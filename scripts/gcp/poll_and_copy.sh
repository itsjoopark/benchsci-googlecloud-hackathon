#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Poll Cloud SQL imports, queue remaining tables, copy to BigQuery.
# Handles the fact that gcloud sql import times out on large files
# but the server-side operation continues.
#
# Usage:  bash scripts/gcp/poll_and_copy.sh
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
GCS_EXPORT_PREFIX="pkg2_exports"
SA_KEY="${REPO_ROOT}/service-account-key.json"

ts() { date +%H:%M:%S; }

# ── Auth ──────────────────────────────────────────────────────────────
if [[ -f "${SA_KEY}" ]]; then
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet 2>/dev/null
fi

bq --project_id="${PROJECT_ID}" mk --dataset "${PROJECT_ID}:${DATASET}" 2>/dev/null || true

# Grant write access to all Cloud SQL instance SAs
for inst in pkg25-import pkg25-import-b pkg25-import-c; do
  SA=$(gcloud sql instances describe "${inst}" \
    --project="${PROJECT_ID}" \
    --format='value(serviceAccountEmailAddress)' 2>/dev/null)
  if [[ -n "${SA}" ]]; then
    gsutil iam ch "serviceAccount:${SA}:objectAdmin" "gs://${BUCKET}" 2>/dev/null || true
  fi
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Poll imports + queue remaining + copy to BigQuery      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Helpers ───────────────────────────────────────────────────────────

wait_for_imports() {
  local instance="$1"
  while true; do
    local running
    running=$(gcloud sql operations list --instance="${instance}" \
      --project="${PROJECT_ID}" \
      --filter="status=RUNNING AND operationType=IMPORT" \
      --format="value(name)" 2>/dev/null | head -1)
    if [[ -z "${running}" ]]; then
      return 0
    fi
    printf "\r[%s] %s: import running (op %s)... " "$(ts)" "${instance}" "${running:0:8}"
    sleep 30
  done
}

import_table() {
  local instance="$1"
  local table="$2"
  local gcs_uri="gs://${BUCKET}/${GCS_SQL_PREFIX}/${table}.sql.gz"

  printf "[%s] Importing %-40s on %s ... " "$(ts)" "${table}" "${instance}"
  T_START=$(date +%s)

  # Use --async to avoid CLI timeout, then poll
  local op_name
  op_name=$(gcloud sql import sql "${instance}" "${gcs_uri}" \
    --database="${DB_NAME}" \
    --project="${PROJECT_ID}" \
    --quiet --async 2>/dev/null | grep -oE '[a-f0-9-]{36}' | head -1)

  if [[ -z "${op_name}" ]]; then
    printf "FAIL (could not start)\n"
    return 1
  fi

  # Poll until done
  while true; do
    local status
    status=$(gcloud sql operations describe "${op_name}" \
      --project="${PROJECT_ID}" \
      --format="value(status)" 2>/dev/null)
    if [[ "${status}" == "DONE" ]]; then
      local err
      err=$(gcloud sql operations describe "${op_name}" \
        --project="${PROJECT_ID}" \
        --format="value(error)" 2>/dev/null)
      if [[ -n "${err}" && "${err}" != "None" ]]; then
        printf "FAIL (%ds) %s\n" "$(( $(date +%s) - T_START ))" "${err}"
        return 1
      fi
      printf "OK  (%ds)\n" "$(( $(date +%s) - T_START ))"
      return 0
    fi
    sleep 30
  done
}

copy_table() {
  local instance="$1"
  local table="$2"
  local GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv.gz"

  printf "[%s] Export+Load %-40s ... " "$(ts)" "${table}"
  T_START=$(date +%s)

  # Export from Cloud SQL
  if ! gcloud sql export csv "${instance}" "${GCS_CSV}" \
       --database="${DB_NAME}" \
       --project="${PROJECT_ID}" \
       --offload \
       --query="SELECT * FROM ${table}" \
       --quiet 2>/tmp/poll_err_${table}.log; then
    printf "EXPORT FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
    head -2 /tmp/poll_err_${table}.log
    return 1
  fi

  # Load into BigQuery
  if ! bq --project_id="${PROJECT_ID}" load \
       --source_format=CSV \
       --autodetect \
       --allow_quoted_newlines \
       --replace \
       "${DATASET}.${table}" \
       "${GCS_CSV}" 2>/tmp/poll_bqerr_${table}.log; then
    printf "BQ FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
    head -2 /tmp/poll_bqerr_${table}.log
    return 1
  fi

  printf "OK  (%ds)\n" "$(( $(date +%s) - T_START ))"
  return 0
}

import_and_copy() {
  local instance="$1"
  local table="$2"
  import_table "${instance}" "${table}" && copy_table "${instance}" "${table}"
}

BQ_PASS=0
BQ_FAIL=0

track() {
  if "$@"; then
    BQ_PASS=$((BQ_PASS + 1))
  else
    BQ_FAIL=$((BQ_FAIL + 1))
  fi
}

# ══════════════════════════════════════════════════════════════════════
# Phase 1: Instance A — wait for C21, then copy the 6 small tables
# ══════════════════════════════════════════════════════════════════════
echo "═══ Instance A: wait for current import, copy 6 small tables ═══"
wait_for_imports pkg25-import
echo ""
echo "[$(ts)] Instance A idle. Copying small tables to BigQuery..."

for table in C23_BioEntities C13_Link_ClinicalTrials_BioEntities C18_Link_Patents_BioEntities C15_Patents C11_ClinicalTrials C21_Bioentity_Relationships; do
  track copy_table pkg25-import "${table}"
done
echo ""

# ══════════════════════════════════════════════════════════════════════
# Phase 2: Instance B — wait for A04, import remaining (A06, C01), copy all
# ══════════════════════════════════════════════════════════════════════
echo "═══ Instance B: wait for A04, import A06+C01, copy all ══════════"
wait_for_imports pkg25-import-b
echo ""
echo "[$(ts)] Instance B: A04 import done. Copying A04..."
track copy_table pkg25-import-b A04_Abstract

echo "[$(ts)] Importing remaining tables on Instance B..."
track import_and_copy pkg25-import-b A06_MeshHeadingList
track import_and_copy pkg25-import-b C01_Papers
echo ""

# ══════════════════════════════════════════════════════════════════════
# Phase 3: Instance C — wait for C06, import remaining (A01, A03), copy all
# ══════════════════════════════════════════════════════════════════════
echo "═══ Instance C: wait for C06, import A01+A03, copy all ══════════"
wait_for_imports pkg25-import-c
echo ""
echo "[$(ts)] Instance C: C06 import done. Copying C06..."
track copy_table pkg25-import-c C06_Link_Papers_BioEntities

echo "[$(ts)] Importing remaining tables on Instance C..."
track import_and_copy pkg25-import-c A01_Articles
track import_and_copy pkg25-import-c A03_KeywordList
echo ""

# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════
echo "═══ Verify Row Counts ════════════════════════════════════════"
for table in C23_BioEntities C13_Link_ClinicalTrials_BioEntities C18_Link_Patents_BioEntities C15_Patents C11_ClinicalTrials C21_Bioentity_Relationships A03_KeywordList C01_Papers A01_Articles A06_MeshHeadingList A04_Abstract C06_Link_Papers_BioEntities; do
  COUNT=$(bq --project_id="${PROJECT_ID}" query \
    --use_legacy_sql=false --format=csv --quiet \
    "SELECT COUNT(*) AS c FROM \`${PROJECT_ID}.${DATASET}.${table}\`" \
    2>/dev/null | tail -1)
  if [[ -n "${COUNT}" && "${COUNT}" != "0" ]]; then
    printf "  %-45s %s rows\n" "${table}" "${COUNT}"
  else
    printf "  %-45s (missing or empty)\n" "${table}"
  fi
done
echo ""

echo "════════════════════════════════════════════════════════════"
echo "  DONE: ${BQ_PASS} OK, ${BQ_FAIL} FAIL"
echo ""
echo "  Delete all instances to stop billing:"
echo "    gcloud sql instances delete pkg25-import pkg25-import-b pkg25-import-c \\"
echo "      --project=${PROJECT_ID} --quiet"
echo "════════════════════════════════════════════════════════════"
