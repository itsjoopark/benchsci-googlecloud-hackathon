#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Fix large tables (A04, C06): re-export WITHOUT --offload to produce
# uncompressed CSV that BigQuery can load (>4GB gzip limit workaround).
# ──────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
BUCKET="multihopwanderer-1771992134-team-bucket"
DB_NAME="PKG25"
GCS_EXPORT_PREFIX="pkg2_exports_v2"
SA_KEY="${REPO_ROOT}/service-account-key.json"

ts() { date +%H:%M:%S; }

if [[ -f "${SA_KEY}" ]]; then
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet 2>/dev/null
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Fix large tables: uncompressed CSV export → BQ load    ║"
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

export_large_table() {
  local instance="$1"
  local table="$2"
  # Uncompressed CSV — no .gz, no --offload
  local GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}_uncompressed.csv"

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

  # Export WITHOUT --offload → uncompressed CSV (no 4GB BQ limit)
  printf "exporting (uncompressed) ... "
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

  # Load to BQ
  printf "loading ... "
  if ! bq --project_id="${PROJECT_ID}" load \
       --source_format=CSV --schema="${bq_schema}" \
       --allow_quoted_newlines --replace \
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
# A04_Abstract on Instance B
# ══════════════════════════════════════════════════════════════════════
echo "═══ A04_Abstract (Instance B) ══════════════════════════════"
wait_for_ops pkg25-import-b
track export_large_table pkg25-import-b A04_Abstract
echo ""

# ══════════════════════════════════════════════════════════════════════
# C06_Link_Papers_BioEntities on Instance C
# ══════════════════════════════════════════════════════════════════════
echo "═══ C06_Link_Papers_BioEntities (Instance C) ══════════════"
wait_for_ops pkg25-import-c
track export_large_table pkg25-import-c C06_Link_Papers_BioEntities
echo ""

# ══════════════════════════════════════════════════════════════════════
echo "════════════════════════════════════════════════════════════"
echo "  DONE: ${PASS} OK, ${FAIL} FAIL"
echo "════════════════════════════════════════════════════════════"
