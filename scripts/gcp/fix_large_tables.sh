#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Fix all 6 failed tables: re-export WITHOUT --offload (uncompressed CSV)
# and strip embedded newlines from text fields via REPLACE().
#
# Fixes two issues:
#   1) >4GB gzip limit: A04, C06, A06
#   2) CSV parsing errors (embedded newlines): A01, C01, A03
# ──────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
BUCKET="multihopwanderer-1771992134-team-bucket"
DB_NAME="PKG25"
GCS_EXPORT_PREFIX="pkg2_exports_v3"
SA_KEY="${REPO_ROOT}/service-account-key.json"

ts() { date +%H:%M:%S; }

if [[ -f "${SA_KEY}" ]]; then
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet 2>/dev/null
fi

# Grant write access to all instance SAs
for inst in pkg25-import pkg25-import-b pkg25-import-c; do
  SA=$(gcloud sql instances describe "${inst}" \
    --project="${PROJECT_ID}" \
    --format='value(serviceAccountEmailAddress)' 2>/dev/null)
  if [[ -n "${SA}" ]]; then
    gsutil iam ch "serviceAccount:${SA}:objectAdmin" "gs://${BUCKET}" 2>/dev/null || true
  fi
done

bq --project_id="${PROJECT_ID}" mk --dataset "${PROJECT_ID}:${DATASET}" 2>/dev/null || true

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Fix 6 tables: uncompressed + newline-stripped → BQ     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

wait_for_ops() {
  local instance="$1"
  local op_type="${2:-}"
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

# Build IFNULL + REPLACE(newlines) query and BQ schema
build_clean_query_and_schema() {
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
        varchar|text|mediumtext|longtext|char)
          # Strip newlines + carriage returns from text, then IFNULL
          cols="${cols}IFNULL(REPLACE(REPLACE(\`${col_name}\`, '\n', ' '), '\r', ' '), '') AS \`${col_name}\`," ;;
        *)
          cols="${cols}IFNULL(REPLACE(REPLACE(\`${col_name}\`, '\n', ' '), '\r', ' '), '') AS \`${col_name}\`," ;;
      esac
    else
      # Non-nullable STRING columns: still strip newlines
      case "${dtype}" in
        int|bigint|double|float|decimal|tinyint|smallint|mediumint|binary|date|datetime|timestamp)
          cols="${cols}\`${col_name}\`," ;;
        *)
          cols="${cols}REPLACE(REPLACE(\`${col_name}\`, '\n', ' '), '\r', ' ') AS \`${col_name}\`," ;;
      esac
    fi
  done <<< "${schema_csv}"
  cols="${cols%,}"
  bq_schema="${bq_schema%,}"
  echo "${cols}|||${bq_schema}"
}

export_and_load_fixed() {
  local instance="$1"
  local table="$2"
  # Uncompressed CSV — no .gz, no --offload
  local GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv"

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
  result=$(build_clean_query_and_schema "${schema_csv}")
  local query="SELECT ${result%%|||*} FROM ${table}"
  local bq_schema="${result##*|||}"

  # Export WITHOUT --offload → uncompressed CSV
  printf "exporting ... "
  wait_for_ops "${instance}"

  if gsutil ls "${GCS_CSV}" >/dev/null 2>&1; then
    printf "(cached) "
  else
    gcloud sql export csv "${instance}" "${GCS_CSV}" \
      --database="${DB_NAME}" --project="${PROJECT_ID}" \
      --query="${query}" --quiet --async 2>/dev/null || true

    wait_for_ops "${instance}" "EXPORT"

    if ! gsutil ls "${GCS_CSV}" >/dev/null 2>&1; then
      printf "EXPORT FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
      return 1
    fi
  fi

  # Load to BQ with max_bad_records as safety net
  printf "loading ... "
  if ! bq --project_id="${PROJECT_ID}" load \
       --source_format=CSV --schema="${bq_schema}" \
       --allow_quoted_newlines --max_bad_records=100 --replace \
       "${DATASET}.${table}" "${GCS_CSV}" 2>/tmp/fix_bqerr_${table}.log; then
    printf "BQ FAIL (%ds)\n" "$(( $(date +%s) - T_START ))"
    head -3 /tmp/fix_bqerr_${table}.log
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
# Instance B: A04, A06, C01 (parallel with Instance C)
# ══════════════════════════════════════════════════════════════════════
run_instance_b() {
  echo "═══ Instance B: A04 + A06 + C01 ═══════════════════════════"
  local B_PASS=0; local B_FAIL=0
  for t in A04_Abstract A06_MeshHeadingList C01_Papers; do
    if export_and_load_fixed pkg25-import-b "${t}"; then
      B_PASS=$((B_PASS + 1))
    else
      B_FAIL=$((B_FAIL + 1))
    fi
  done
  echo "  Instance B: ${B_PASS} OK, ${B_FAIL} FAIL"
  return ${B_FAIL}
}

# ══════════════════════════════════════════════════════════════════════
# Instance C: C06, A01, A03 (parallel with Instance B)
# ══════════════════════════════════════════════════════════════════════
run_instance_c() {
  echo "═══ Instance C: C06 + A01 + A03 ═══════════════════════════"
  local C_PASS=0; local C_FAIL=0
  for t in C06_Link_Papers_BioEntities A01_Articles A03_KeywordList; do
    if export_and_load_fixed pkg25-import-c "${t}"; then
      C_PASS=$((C_PASS + 1))
    else
      C_FAIL=$((C_FAIL + 1))
    fi
  done
  echo "  Instance C: ${C_PASS} OK, ${C_FAIL} FAIL"
  return ${C_FAIL}
}

# Run both instances in parallel (different instances → no conflicts)
echo "[$(ts)] Launching Instance B and C in parallel..."
echo ""

run_instance_b > /tmp/fix_instB.log 2>&1 &
PID_B=$!
run_instance_c > /tmp/fix_instC.log 2>&1 &
PID_C=$!

B_RC=0; C_RC=0
wait ${PID_B} || B_RC=$?
cat /tmp/fix_instB.log
echo ""

wait ${PID_C} || C_RC=$?
cat /tmp/fix_instC.log
echo ""

# ══════════════════════════════════════════════════════════════════════
# Verify all 12 tables
# ══════════════════════════════════════════════════════════════════════
echo "═══ Verify All 12 Tables ═══════════════════════════════════"
TOTAL_OK=0; TOTAL_MISS=0
for t in C23_BioEntities C13_Link_ClinicalTrials_BioEntities C18_Link_Patents_BioEntities C15_Patents C11_ClinicalTrials C21_Bioentity_Relationships A04_Abstract A06_MeshHeadingList C01_Papers C06_Link_Papers_BioEntities A01_Articles A03_KeywordList; do
  COUNT=$(bq --project_id="${PROJECT_ID}" query \
    --use_legacy_sql=false --format=csv --quiet \
    "SELECT COUNT(*) AS c FROM \`${PROJECT_ID}.${DATASET}.${t}\`" \
    2>/dev/null | tail -1)
  if [[ -n "${COUNT}" && "${COUNT}" != "0" && ! "${COUNT}" =~ "Not found" ]]; then
    printf "  %-45s %s rows\n" "${t}" "${COUNT}"
    TOTAL_OK=$((TOTAL_OK + 1))
  else
    printf "  %-45s (missing or empty)\n" "${t}"
    TOTAL_MISS=$((TOTAL_MISS + 1))
  fi
done
echo ""

echo "════════════════════════════════════════════════════════════"
echo "  ${TOTAL_OK}/12 tables loaded, ${TOTAL_MISS} missing"
echo ""
echo "  Delete all instances to stop billing:"
echo "    gcloud sql instances delete pkg25-import pkg25-import-b pkg25-import-c \\"
echo "      --project=${PROJECT_ID} --quiet"
echo "════════════════════════════════════════════════════════════"
