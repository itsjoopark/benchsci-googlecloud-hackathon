#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Finish the pipeline: wait for pending ops, import remaining tables,
# export all to BigQuery with proper schema + IFNULL.
#
# Handles CLI timeouts by polling server-side operations.
# ──────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
BUCKET="multihopwanderer-1771992134-team-bucket"
REGION="us-central1"
DB_NAME="PKG25"
GCS_SQL_PREFIX="pkg2_sql"
GCS_EXPORT_PREFIX="pkg2_exports_v2"
SA_KEY="${REPO_ROOT}/service-account-key.json"

ts() { date +%H:%M:%S; }

if [[ -f "${SA_KEY}" ]]; then
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet 2>/dev/null
fi

bq --project_id="${PROJECT_ID}" mk --dataset "${PROJECT_ID}:${DATASET}" 2>/dev/null || true

# Grant write access
for inst in pkg25-import pkg25-import-b pkg25-import-c; do
  SA=$(gcloud sql instances describe "${inst}" \
    --project="${PROJECT_ID}" \
    --format='value(serviceAccountEmailAddress)' 2>/dev/null)
  if [[ -n "${SA}" ]]; then
    gsutil iam ch "serviceAccount:${SA}:objectAdmin" "gs://${BUCKET}" 2>/dev/null || true
  fi
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Finish Pipeline: import remaining + export all to BQ   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Helpers ───────────────────────────────────────────────────────────

wait_for_ops() {
  local instance="$1"
  local op_type="${2:-}"  # IMPORT or EXPORT or empty for any
  local filter="status=RUNNING"
  if [[ -n "${op_type}" ]]; then
    filter="${filter} AND operationType=${op_type}"
  fi
  while true; do
    local running
    running=$(gcloud sql operations list --instance="${instance}" \
      --project="${PROJECT_ID}" --filter="${filter}" \
      --format="value(name)" 2>/dev/null | head -1)
    if [[ -z "${running}" ]]; then
      return 0
    fi
    printf "\r[%s] %s: %s running... " "$(ts)" "${instance}" "${op_type:-op}"
    sleep 20
  done
}

import_async() {
  local instance="$1"
  local table="$2"
  local gcs_uri="gs://${BUCKET}/${GCS_SQL_PREFIX}/${table}.sql.gz"

  printf "[%s] Importing %-40s on %s ... " "$(ts)" "${table}" "${instance}"
  local T_START=$(date +%s)

  gcloud sql import sql "${instance}" "${gcs_uri}" \
    --database="${DB_NAME}" --project="${PROJECT_ID}" \
    --quiet --async 2>/dev/null || true

  # Poll until done
  wait_for_ops "${instance}" "IMPORT"
  printf "done (%ds)\n" "$(( $(date +%s) - T_START ))"
}

get_schema_csv() {
  local instance="$1"
  local table="$2"

  wait_for_ops "${instance}"
  gcloud sql export csv "${instance}" \
    "gs://${BUCKET}/${GCS_EXPORT_PREFIX}/_schema_${table}.csv" \
    --database="${DB_NAME}" --project="${PROJECT_ID}" \
    --query="SELECT COLUMN_NAME, IS_NULLABLE, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='${DB_NAME}' AND TABLE_NAME='${table}' ORDER BY ORDINAL_POSITION" \
    --quiet 2>/dev/null
  gsutil cat "gs://${BUCKET}/${GCS_EXPORT_PREFIX}/_schema_${table}.csv" 2>/dev/null
}

build_ifnull_and_schema() {
  local schema_csv="$1"

  local cols=""
  local bq_schema=""
  while IFS= read -r line; do
    local col_name=$(echo "${line}" | sed 's/^"\([^"]*\)".*/\1/')
    local nullable=$(echo "${line}" | sed 's/^"[^"]*","\([^"]*\)".*/\1/')
    local dtype=$(echo "${line}" | sed 's/^"[^"]*","[^"]*","\([^"]*\)"/\1/')

    local bq_type="STRING"
    case "${dtype}" in
      int|tinyint|smallint|mediumint) bq_type="INT64" ;;
      bigint)                         bq_type="INT64" ;;
      double|float|decimal)           bq_type="FLOAT64" ;;
      binary)                         bq_type="INT64" ;;
      *)                              bq_type="STRING" ;;
    esac
    bq_schema="${bq_schema}${col_name}:${bq_type},"

    if [[ "${nullable}" == "YES" ]]; then
      case "${dtype}" in
        int|bigint|double|float|decimal|tinyint|smallint|mediumint)
          cols="${cols}IFNULL(\`${col_name}\`, 0) AS \`${col_name}\`," ;;
        date|datetime|timestamp)
          cols="${cols}IFNULL(CAST(\`${col_name}\` AS CHAR), '') AS \`${col_name}\`," ;;
        binary)
          cols="${cols}IFNULL(\`${col_name}\`, 0) AS \`${col_name}\`," ;;
        *)
          cols="${cols}IFNULL(\`${col_name}\`, '') AS \`${col_name}\`," ;;
      esac
    else
      cols="${cols}\`${col_name}\`,"
    fi
  done <<< "${schema_csv}"

  cols="${cols%,}"
  bq_schema="${bq_schema%,}"
  echo "${cols}|||${bq_schema}"
}

export_and_load() {
  local instance="$1"
  local table="$2"
  local GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv.gz"

  printf "[%s] %-45s " "$(ts)" "${table}"
  local T_START=$(date +%s)

  # Get schema
  printf "schema ... "
  local schema_csv
  schema_csv=$(get_schema_csv "${instance}" "${table}")
  if [[ -z "${schema_csv}" ]]; then
    printf "SCHEMA FAIL\n"
    return 1
  fi

  local result
  result=$(build_ifnull_and_schema "${schema_csv}")
  local query="SELECT ${result%%|||*} FROM ${table}"
  local bq_schema="${result##*|||}"

  # Export (async + poll to avoid CLI timeout)
  printf "exporting ... "
  wait_for_ops "${instance}"

  # Reuse existing CSV if already exported (e.g. from a prior run)
  if gsutil ls "${GCS_CSV}" >/dev/null 2>&1; then
    printf "(cached) "
  else
    gcloud sql export csv "${instance}" "${GCS_CSV}" \
      --database="${DB_NAME}" --project="${PROJECT_ID}" \
      --offload --query="${query}" --quiet --async 2>/dev/null || \
    gcloud sql export csv "${instance}" "${GCS_CSV}" \
      --database="${DB_NAME}" --project="${PROJECT_ID}" \
      --offload --query="${query}" --quiet --async 2>/dev/null || true

    wait_for_ops "${instance}" "EXPORT"

    # Check export succeeded (file exists)
    if ! gsutil ls "${GCS_CSV}" >/dev/null 2>&1; then
      printf "EXPORT FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
      return 1
    fi
  fi

  # Load to BQ
  printf "loading ... "
  if ! bq --project_id="${PROJECT_ID}" load \
       --source_format=CSV --schema="${bq_schema}" \
       --allow_quoted_newlines --replace \
       "${DATASET}.${table}" "${GCS_CSV}" 2>/tmp/finish_bqerr_${table}.log; then
    printf "BQ FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
    head -2 /tmp/finish_bqerr_${table}.log
    return 1
  fi

  printf "OK (%ds)\n" "$(( $(date +%s) - T_START ))"
  return 0
}

PASS=0
FAIL=0
track() {
  if "$@"; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); fi
}

# ══════════════════════════════════════════════════════════════════════
# Instance A: SKIPPED — handled by running bb3743e (reexport_to_bq.sh)
# ══════════════════════════════════════════════════════════════════════
echo "═══ Instance A: SKIPPED (handled by reexport_to_bq.sh) ═════"
echo ""

# ══════════════════════════════════════════════════════════════════════
# Instance B: A04 (wait for export), then import+export A06 and C01
# ══════════════════════════════════════════════════════════════════════
echo "═══ Instance B: A04 + A06 + C01 → BQ ════════════════════════"
echo "[$(ts)] Waiting for A04 export to finish..."
wait_for_ops pkg25-import-b
echo ""
track export_and_load pkg25-import-b A04_Abstract
import_async pkg25-import-b A06_MeshHeadingList
track export_and_load pkg25-import-b A06_MeshHeadingList
import_async pkg25-import-b C01_Papers
track export_and_load pkg25-import-b C01_Papers
echo ""

# ══════════════════════════════════════════════════════════════════════
# Instance C: C06 (wait for import), then import+export A01 and A03
# ══════════════════════════════════════════════════════════════════════
echo "═══ Instance C: C06 + A01 + A03 → BQ ════════════════════════"
echo "[$(ts)] Waiting for C06 import to finish..."
wait_for_ops pkg25-import-c "IMPORT"
echo ""
track export_and_load pkg25-import-c C06_Link_Papers_BioEntities
import_async pkg25-import-c A01_Articles
track export_and_load pkg25-import-c A01_Articles
import_async pkg25-import-c A03_KeywordList
track export_and_load pkg25-import-c A03_KeywordList
echo ""

# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════
echo "═══ Verify Row Counts ════════════════════════════════════════"
for t in C23_BioEntities C13_Link_ClinicalTrials_BioEntities C18_Link_Patents_BioEntities C15_Patents C11_ClinicalTrials C21_Bioentity_Relationships A03_KeywordList C01_Papers A01_Articles A06_MeshHeadingList A04_Abstract C06_Link_Papers_BioEntities; do
  COUNT=$(bq --project_id="${PROJECT_ID}" query \
    --use_legacy_sql=false --format=csv --quiet \
    "SELECT COUNT(*) AS c FROM \`${PROJECT_ID}.${DATASET}.${t}\`" \
    2>/dev/null | tail -1)
  if [[ -n "${COUNT}" && "${COUNT}" != "0" ]]; then
    printf "  %-45s %s rows\n" "${t}" "${COUNT}"
  else
    printf "  %-45s (missing or empty)\n" "${t}"
  fi
done
echo ""

echo "════════════════════════════════════════════════════════════"
echo "  DONE: ${PASS} OK, ${FAIL} FAIL"
echo ""
echo "  Delete all instances to stop billing:"
echo "    gcloud sql instances delete pkg25-import pkg25-import-b pkg25-import-c \\"
echo "      --project=${PROJECT_ID} --quiet"
echo "════════════════════════════════════════════════════════════"
