#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Load PKG 2.5 MySQL dumps → BigQuery via Cloud SQL
#
# Pipeline:
#   data/pkg2_sql/*.sql.gz → GCS → Cloud SQL MySQL → BigQuery
#
# Usage:
#   bash scripts/gcp/load_sql_via_cloudsql.sh          # full pipeline
#   bash scripts/gcp/load_sql_via_cloudsql.sh --skip-upload   # skip GCS upload
#   bash scripts/gcp/load_sql_via_cloudsql.sh --skip-instance # reuse existing instance
#   bash scripts/gcp/load_sql_via_cloudsql.sh --cleanup-only  # just delete instance
# ──────────────────────────────────────────────────────────────────────
set -uo pipefail

# ── Configuration ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
INSTANCE_NAME="pkg25-import"
BUCKET="multihopwanderer-1771992134-team-bucket"
REGION="us-central1"
DB_NAME="PKG25"
GCS_SQL_PREFIX="pkg2_sql"
GCS_EXPORT_PREFIX="pkg2_exports"
CONNECTION_ID="pkg25-conn"

SA_KEY="${REPO_ROOT}/service-account-key.json"
DATA_DIR="${REPO_ROOT}/data/pkg2_sql"
RESULT_DIR="$(mktemp -d)"
trap 'rm -rf "${RESULT_DIR}"' EXIT

# Tables ordered by size (smallest first for faster early feedback)
TABLES=(
  C23_BioEntities
  C13_Link_ClinicalTrials_BioEntities
  C18_Link_Patents_BioEntities
  C15_Patents
  C11_ClinicalTrials
  C21_Bioentity_Relationships
  A03_KeywordList
  C01_Papers
  A01_Articles
  A06_MeshHeadingList
  A04_Abstract
  C06_Link_Papers_BioEntities
)

# Tables too large for federated query (>20GB result); use CSV export path
LARGE_TABLES=(
  A04_Abstract
  C06_Link_Papers_BioEntities
)

# ── Parse flags ───────────────────────────────────────────────────────
SKIP_UPLOAD=false
SKIP_INSTANCE=false
CLEANUP_ONLY=false

for arg in "$@"; do
  case "${arg}" in
    --skip-upload)    SKIP_UPLOAD=true ;;
    --skip-instance)  SKIP_INSTANCE=true ;;
    --cleanup-only)   CLEANUP_ONLY=true ;;
    *) echo "Unknown flag: ${arg}"; exit 1 ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────
ts() { date +%H:%M:%S; }

is_large_table() {
  local table="$1"
  for lt in "${LARGE_TABLES[@]}"; do
    [[ "${lt}" == "${table}" ]] && return 0
  done
  return 1
}

# ══════════════════════════════════════════════════════════════════════
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  MySQL Dumps → BigQuery via Cloud SQL                   ║"
echo "║  Project : ${PROJECT_ID}                ║"
echo "║  Instance: ${INSTANCE_NAME}  Region: ${REGION}              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

PIPELINE_START=$(date +%s)

# ──────────────────────────────────────────────────────────────────────
# Step 0: Cleanup-only mode
# ──────────────────────────────────────────────────────────────────────
if [[ "${CLEANUP_ONLY}" == "true" ]]; then
  echo "═══ Cleanup Only Mode ══════════════════════════════════════"
  echo "[$(ts)] Deleting Cloud SQL instance ${INSTANCE_NAME}..."
  if gcloud sql instances describe "${INSTANCE_NAME}" \
       --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud sql instances delete "${INSTANCE_NAME}" \
      --project="${PROJECT_ID}" --quiet
    echo "[$(ts)] Instance deleted."
  else
    echo "[$(ts)] Instance does not exist — nothing to delete."
  fi

  echo "[$(ts)] Deleting BigQuery connection ${CONNECTION_ID}..."
  bq rm --connection --location="${REGION}" \
    "${PROJECT_ID}.${REGION}.${CONNECTION_ID}" 2>/dev/null || true
  echo "[$(ts)] Done."
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# Step 1: Prerequisites
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 1: Prerequisites ════════════════════════════════════"

for cmd in gcloud bq gsutil; do
  command -v "${cmd}" >/dev/null 2>&1 || {
    echo "ERROR: ${cmd} not found on PATH"; exit 1
  }
done
echo "[$(ts)] gcloud, bq, gsutil — OK"

# Verify local dump files
MISSING=0
for table in "${TABLES[@]}"; do
  if [[ ! -f "${DATA_DIR}/${table}.sql.gz" ]]; then
    echo "  MISSING: ${DATA_DIR}/${table}.sql.gz"
    MISSING=$((MISSING + 1))
  fi
done
if [[ ${MISSING} -gt 0 ]]; then
  echo "ERROR: ${MISSING} dump file(s) not found in ${DATA_DIR}/"
  exit 1
fi
echo "[$(ts)] All ${#TABLES[@]} dump files present in ${DATA_DIR}/"

# Activate service account key (needed for Cloud SQL import/export perms)
if [[ -f "${SA_KEY}" ]]; then
  echo "[$(ts)] Activating service account key..."
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet
  echo "[$(ts)] Authenticated as $(gcloud config get-value account 2>/dev/null)"
else
  echo "WARNING: Service account key not found at ${SA_KEY}"
  echo "         Cloud SQL import may fail without roles/editor."
fi

# Enable required APIs
echo "[$(ts)] Enabling Cloud SQL Admin API..."
gcloud services enable sqladmin.googleapis.com \
  --project="${PROJECT_ID}" --quiet 2>/dev/null || true

echo "[$(ts)] Enabling BigQuery Connection API..."
gcloud services enable bigqueryconnection.googleapis.com \
  --project="${PROJECT_ID}" --quiet 2>/dev/null || true

echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 2: Upload dumps to GCS
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 2: Upload Dumps to GCS ══════════════════════════════"

if [[ "${SKIP_UPLOAD}" == "true" ]]; then
  echo "[$(ts)] --skip-upload: skipping GCS upload"
else
  # Check which files already exist in GCS
  EXISTING_GCS="$(gsutil ls "gs://${BUCKET}/${GCS_SQL_PREFIX}/" 2>/dev/null || true)"
  UPLOAD_NEEDED=()

  for table in "${TABLES[@]}"; do
    fname="${table}.sql.gz"
    if echo "${EXISTING_GCS}" | grep -q "${fname}"; then
      echo "  SKIP (exists): ${fname}"
    else
      UPLOAD_NEEDED+=("${DATA_DIR}/${fname}")
    fi
  done

  if [[ ${#UPLOAD_NEEDED[@]} -eq 0 ]]; then
    echo "[$(ts)] All files already in GCS — nothing to upload"
  else
    echo "[$(ts)] Uploading ${#UPLOAD_NEEDED[@]} file(s) to gs://${BUCKET}/${GCS_SQL_PREFIX}/..."
    UPLOAD_START=$(date +%s)
    gsutil -m cp "${UPLOAD_NEEDED[@]}" "gs://${BUCKET}/${GCS_SQL_PREFIX}/"
    UPLOAD_ELAPSED=$(( $(date +%s) - UPLOAD_START ))
    echo "[$(ts)] Upload complete in ${UPLOAD_ELAPSED}s"
  fi
fi
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 3: Create Cloud SQL Instance
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 3: Create Cloud SQL Instance ════════════════════════"

if [[ "${SKIP_INSTANCE}" == "true" ]]; then
  echo "[$(ts)] --skip-instance: reusing existing instance"
else
  # Check if instance already exists
  if gcloud sql instances describe "${INSTANCE_NAME}" \
       --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "[$(ts)] Instance ${INSTANCE_NAME} already exists — reusing"
  else
    echo "[$(ts)] Creating Cloud SQL instance ${INSTANCE_NAME}..."
    echo "         tier=db-custom-4-16384  storage=500GB SSD"
    INSTANCE_START=$(date +%s)

    gcloud sql instances create "${INSTANCE_NAME}" \
      --project="${PROJECT_ID}" \
      --database-version=MYSQL_8_0 \
      --tier=db-custom-4-16384 \
      --storage-size=500 \
      --storage-type=SSD \
      --region="${REGION}" \
      --no-backup \
      --database-flags=innodb_flush_log_at_trx_commit=2 \
      --quiet

    rc=$?
    if [[ ${rc} -ne 0 ]]; then
      echo "ERROR: Cloud SQL instance creation failed (exit code ${rc})"
      exit 1
    fi

    INSTANCE_ELAPSED=$(( $(date +%s) - INSTANCE_START ))
    echo "[$(ts)] Instance created in ${INSTANCE_ELAPSED}s"
  fi

  # Create database if it doesn't exist
  echo "[$(ts)] Ensuring database ${DB_NAME} exists..."
  gcloud sql databases create "${DB_NAME}" \
    --instance="${INSTANCE_NAME}" \
    --project="${PROJECT_ID}" --quiet 2>/dev/null || true
fi
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 4: Grant GCS Access & Import Dumps
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 4: Import SQL Dumps into Cloud SQL ══════════════════"

# Grant the Cloud SQL service account read access to our GCS bucket
SA=$(gcloud sql instances describe "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --format='value(serviceAccountEmailAddress)')
echo "[$(ts)] Cloud SQL SA: ${SA}"
echo "[$(ts)] Granting objectViewer on gs://${BUCKET}/..."
gsutil iam ch "serviceAccount:${SA}:objectViewer" "gs://${BUCKET}" 2>/dev/null || true

IMPORT_PASS=0
IMPORT_FAIL=0

for table in "${TABLES[@]}"; do
  GCS_URI="gs://${BUCKET}/${GCS_SQL_PREFIX}/${table}.sql.gz"
  printf "[%s] Importing %-45s ... " "$(ts)" "${table}"

  TABLE_START=$(date +%s)
  if gcloud sql import sql "${INSTANCE_NAME}" "${GCS_URI}" \
       --database="${DB_NAME}" \
       --project="${PROJECT_ID}" \
       --quiet 2>"${RESULT_DIR}/${table}.import.err"; then
    TABLE_ELAPSED=$(( $(date +%s) - TABLE_START ))
    printf "OK  (%ds)\n" "${TABLE_ELAPSED}"
    echo "OK" > "${RESULT_DIR}/${table}.import.status"
    IMPORT_PASS=$((IMPORT_PASS + 1))
  else
    TABLE_ELAPSED=$(( $(date +%s) - TABLE_START ))
    printf "FAIL (%ds)\n" "${TABLE_ELAPSED}"
    echo "FAIL" > "${RESULT_DIR}/${table}.import.status"
    echo "  Error: $(head -1 "${RESULT_DIR}/${table}.import.err")"
    IMPORT_FAIL=$((IMPORT_FAIL + 1))
  fi
done

echo ""
echo "[$(ts)] Import summary: ${IMPORT_PASS} OK, ${IMPORT_FAIL} FAIL"

if [[ ${IMPORT_FAIL} -gt 0 ]]; then
  echo "WARNING: Some imports failed. Continuing with successfully imported tables."
fi
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 5: Copy to BigQuery
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 5: Copy Tables to BigQuery ══════════════════════════"

# Create dataset if needed
bq --project_id="${PROJECT_ID}" mk --dataset \
  "${PROJECT_ID}:${DATASET}" 2>/dev/null || true
echo "[$(ts)] Dataset ${DATASET} ready"

# Create BigQuery connection for federated queries
INSTANCE_CONN_NAME="${PROJECT_ID}:${REGION}:${INSTANCE_NAME}"
echo "[$(ts)] Creating BigQuery connection ${CONNECTION_ID}..."

# Remove existing connection (if any) to avoid conflicts
bq rm --connection --location="${REGION}" \
  "${PROJECT_ID}.${REGION}.${CONNECTION_ID}" 2>/dev/null || true

bq mk --connection --connection_type=CLOUD_SQL \
  --properties="{\"instanceId\":\"${INSTANCE_CONN_NAME}\",\"database\":\"${DB_NAME}\",\"type\":\"MYSQL\"}" \
  --project_id="${PROJECT_ID}" \
  --location="${REGION}" \
  "${CONNECTION_ID}" 2>/dev/null || {
    echo "WARNING: Could not create BigQuery connection."
    echo "         Will use CSV export path for all tables."
  }

BQ_PASS=0
BQ_FAIL=0

for table in "${TABLES[@]}"; do
  # Skip tables that failed import
  if [[ -f "${RESULT_DIR}/${table}.import.status" ]] && \
     [[ "$(cat "${RESULT_DIR}/${table}.import.status")" != "OK" ]]; then
    printf "[%s] %-45s SKIP (import failed)\n" "$(ts)" "${table}"
    continue
  fi

  FULL_TABLE="${PROJECT_ID}:${DATASET}.${table}"
  printf "[%s] Copying %-45s ... " "$(ts)" "${table}"
  TABLE_START=$(date +%s)

  if is_large_table "${table}"; then
    # ── Large table: CSV export → GCS → bq load ────────────────
    GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv.gz"

    # Export from Cloud SQL to GCS as CSV
    if ! gcloud sql export csv "${INSTANCE_NAME}" "${GCS_CSV}" \
           --database="${DB_NAME}" \
           --project="${PROJECT_ID}" \
           --offload \
           --query="SELECT * FROM ${table}" \
           --quiet 2>"${RESULT_DIR}/${table}.export.err"; then
      TABLE_ELAPSED=$(( $(date +%s) - TABLE_START ))
      printf "FAIL (export, %ds)\n" "${TABLE_ELAPSED}"
      echo "  Error: $(head -1 "${RESULT_DIR}/${table}.export.err")"
      BQ_FAIL=$((BQ_FAIL + 1))
      echo "FAIL" > "${RESULT_DIR}/${table}.bq.status"
      continue
    fi

    # Load CSV into BigQuery
    if ! bq --project_id="${PROJECT_ID}" load \
           --source_format=CSV \
           --autodetect \
           --allow_quoted_newlines \
           --replace \
           "${DATASET}.${table}" \
           "${GCS_CSV}" 2>"${RESULT_DIR}/${table}.bqload.err"; then
      TABLE_ELAPSED=$(( $(date +%s) - TABLE_START ))
      printf "FAIL (bq load, %ds)\n" "${TABLE_ELAPSED}"
      echo "  Error: $(head -1 "${RESULT_DIR}/${table}.bqload.err")"
      BQ_FAIL=$((BQ_FAIL + 1))
      echo "FAIL" > "${RESULT_DIR}/${table}.bq.status"
      continue
    fi
  else
    # ── Small/medium table: federated query ────────────────────
    BQ_CONN="${PROJECT_ID}.${REGION}.${CONNECTION_ID}"
    if ! bq --project_id="${PROJECT_ID}" query \
           --use_legacy_sql=false \
           --destination_table="${DATASET}.${table}" \
           --replace \
           "SELECT * FROM EXTERNAL_QUERY('${BQ_CONN}', 'SELECT * FROM ${table}')" \
           2>"${RESULT_DIR}/${table}.fedq.err"; then

      # Fallback: try CSV export path if federated query fails
      printf "fedq fail, trying CSV ... "
      GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv.gz"

      if gcloud sql export csv "${INSTANCE_NAME}" "${GCS_CSV}" \
             --database="${DB_NAME}" \
             --project="${PROJECT_ID}" \
             --offload \
             --query="SELECT * FROM ${table}" \
             --quiet 2>/dev/null && \
         bq --project_id="${PROJECT_ID}" load \
             --source_format=CSV \
             --autodetect \
             --allow_quoted_newlines \
             --replace \
             "${DATASET}.${table}" \
             "${GCS_CSV}" 2>/dev/null; then
        : # success via fallback
      else
        TABLE_ELAPSED=$(( $(date +%s) - TABLE_START ))
        printf "FAIL (%ds)\n" "${TABLE_ELAPSED}"
        BQ_FAIL=$((BQ_FAIL + 1))
        echo "FAIL" > "${RESULT_DIR}/${table}.bq.status"
        continue
      fi
    fi
  fi

  TABLE_ELAPSED=$(( $(date +%s) - TABLE_START ))
  printf "OK  (%ds)\n" "${TABLE_ELAPSED}"
  echo "OK" > "${RESULT_DIR}/${table}.bq.status"
  BQ_PASS=$((BQ_PASS + 1))
done

echo ""
echo "[$(ts)] BigQuery copy summary: ${BQ_PASS} OK, ${BQ_FAIL} FAIL"
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 6: Verify Row Counts
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 6: Verify Row Counts ════════════════════════════════"

for table in "${TABLES[@]}"; do
  if [[ -f "${RESULT_DIR}/${table}.bq.status" ]] && \
     [[ "$(cat "${RESULT_DIR}/${table}.bq.status")" == "OK" ]]; then
    COUNT=$(bq --project_id="${PROJECT_ID}" query \
      --use_legacy_sql=false --format=csv --quiet \
      "SELECT COUNT(*) AS c FROM \`${PROJECT_ID}.${DATASET}.${table}\`" \
      2>/dev/null | tail -1)
    printf "  %-45s %s rows\n" "${table}" "${COUNT}"
  else
    printf "  %-45s (skipped)\n" "${table}"
  fi
done
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 7: Cleanup prompt
# ──────────────────────────────────────────────────────────────────────
echo "═══ Step 7: Cleanup ══════════════════════════════════════════"
PIPELINE_ELAPSED=$(( $(date +%s) - PIPELINE_START ))
PIPELINE_MIN=$(( PIPELINE_ELAPSED / 60 ))
echo "[$(ts)] Pipeline completed in ${PIPELINE_MIN}m ${PIPELINE_ELAPSED}s total"
echo ""
echo "Cloud SQL instance '${INSTANCE_NAME}' is still running (~\$0.80/hr)."
echo "To delete it and stop billing:"
echo ""
echo "  bash scripts/gcp/load_sql_via_cloudsql.sh --cleanup-only"
echo ""
echo "Or manually:"
echo "  gcloud sql instances delete ${INSTANCE_NAME} --project=${PROJECT_ID} --quiet"
echo ""

# ── Final summary ─────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════"
echo "  SUMMARY"
echo "════════════════════════════════════════════════════════════"
printf "  %-25s %s\n" "Import to Cloud SQL:" "${IMPORT_PASS}/${#TABLES[@]} OK"
printf "  %-25s %s\n" "Copy to BigQuery:" "${BQ_PASS}/${#TABLES[@]} OK"
printf "  %-25s %s\n" "Total time:" "${PIPELINE_MIN}m $(( PIPELINE_ELAPSED % 60 ))s"
echo "════════════════════════════════════════════════════════════"

if [[ ${IMPORT_FAIL} -gt 0 || ${BQ_FAIL} -gt 0 ]]; then
  exit 1
fi
