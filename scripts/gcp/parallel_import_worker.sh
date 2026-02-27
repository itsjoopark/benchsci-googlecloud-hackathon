#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Parallel import worker: creates a Cloud SQL instance, imports assigned
# tables, copies them to BigQuery, then cleans up.
#
# Usage:
#   bash scripts/gcp/parallel_import_worker.sh <instance-name> <table1> [table2] ...
# ──────────────────────────────────────────────────────────────────────
set -uo pipefail

INSTANCE_NAME="${1:?Usage: $0 <instance-name> <table1> [table2] ...}"
shift
TABLES=("$@")

if [[ ${#TABLES[@]} -eq 0 ]]; then
  echo "ERROR: No tables specified"
  exit 1
fi

# ── Configuration ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
BUCKET="multihopwanderer-1771992134-team-bucket"
REGION="us-central1"
DB_NAME="PKG25"
GCS_SQL_PREFIX="pkg2_sql"
GCS_EXPORT_PREFIX="pkg2_exports"
SA_KEY="${REPO_ROOT}/service-account-key.json"

ts() { date +%H:%M:%S; }

echo "════════════════════════════════════════════════════════════"
echo "  Worker: ${INSTANCE_NAME}"
echo "  Tables: ${TABLES[*]}"
echo "════════════════════════════════════════════════════════════"

# ── Auth ──────────────────────────────────────────────────────────────
if [[ -f "${SA_KEY}" ]]; then
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet 2>/dev/null
fi

# ── Create instance ───────────────────────────────────────────────────
if gcloud sql instances describe "${INSTANCE_NAME}" \
     --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "[$(ts)] Instance ${INSTANCE_NAME} already exists — reusing"
else
  echo "[$(ts)] Creating instance ${INSTANCE_NAME}..."
  INST_START=$(date +%s)
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
    echo "ERROR: Instance creation failed"
    exit 1
  fi
  echo "[$(ts)] Instance created in $(( $(date +%s) - INST_START ))s"
fi

# Create database
gcloud sql databases create "${DB_NAME}" \
  --instance="${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" --quiet 2>/dev/null || true

# Grant GCS access
SA=$(gcloud sql instances describe "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --format='value(serviceAccountEmailAddress)')
gsutil iam ch "serviceAccount:${SA}:objectViewer" "gs://${BUCKET}" 2>/dev/null || true

# ── Import tables ─────────────────────────────────────────────────────
echo ""
IMPORT_PASS=0
for table in "${TABLES[@]}"; do
  GCS_URI="gs://${BUCKET}/${GCS_SQL_PREFIX}/${table}.sql.gz"
  printf "[%s] Importing %-45s ... " "$(ts)" "${table}"
  T_START=$(date +%s)

  if gcloud sql import sql "${INSTANCE_NAME}" "${GCS_URI}" \
       --database="${DB_NAME}" \
       --project="${PROJECT_ID}" \
       --quiet 2>/dev/null; then
    printf "OK  (%ds)\n" "$(( $(date +%s) - T_START ))"
    IMPORT_PASS=$((IMPORT_PASS + 1))
  else
    printf "FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
  fi
done

echo ""
echo "[$(ts)] Import: ${IMPORT_PASS}/${#TABLES[@]} OK"

# ── Copy to BigQuery via CSV export ───────────────────────────────────
echo ""
BQ_PASS=0
for table in "${TABLES[@]}"; do
  GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv.gz"
  printf "[%s] Exporting+Loading %-38s ... " "$(ts)" "${table}"
  T_START=$(date +%s)

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
    printf "OK  (%ds)\n" "$(( $(date +%s) - T_START ))"
    BQ_PASS=$((BQ_PASS + 1))
  else
    printf "FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
  fi
done

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Worker ${INSTANCE_NAME} done: ${BQ_PASS}/${#TABLES[@]} in BigQuery"
echo "════════════════════════════════════════════════════════════"
