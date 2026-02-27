#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Re-export Cloud SQL tables to BigQuery using IFNULL to fix NULL issue.
#
# Cloud SQL CSV export writes NULLs as \N which BigQuery can't parse.
# This script wraps every nullable column in IFNULL(col, '') to produce
# clean CSV that BigQuery can ingest.
#
# Usage:  bash scripts/gcp/reexport_to_bq.sh <instance> <table1> [table2...]
#     or: bash scripts/gcp/reexport_to_bq.sh --all-from-a
# ──────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
BUCKET="multihopwanderer-1771992134-team-bucket"
REGION="us-central1"
DB_NAME="PKG25"
GCS_EXPORT_PREFIX="pkg2_exports_v2"
SA_KEY="${REPO_ROOT}/service-account-key.json"

ts() { date +%H:%M:%S; }

if [[ -f "${SA_KEY}" ]]; then
  gcloud auth activate-service-account --key-file="${SA_KEY}" --quiet 2>/dev/null
fi

bq --project_id="${PROJECT_ID}" mk --dataset "${PROJECT_ID}:${DATASET}" 2>/dev/null || true

# Grant write access to Cloud SQL SAs
for inst in pkg25-import pkg25-import-b pkg25-import-c; do
  SA=$(gcloud sql instances describe "${inst}" \
    --project="${PROJECT_ID}" \
    --format='value(serviceAccountEmailAddress)' 2>/dev/null)
  if [[ -n "${SA}" ]]; then
    gsutil iam ch "serviceAccount:${SA}:objectAdmin" "gs://${BUCKET}" 2>/dev/null || true
  fi
done

# ── Build IFNULL query + BQ schema for a table ───────────────────────
# Sets two global vars: BUILT_QUERY and BUILT_SCHEMA
build_query_and_schema() {
  local instance="$1"
  local table="$2"

  BUILT_QUERY=""
  BUILT_SCHEMA=""

  # Get schema from MySQL
  local schema_csv
  gcloud sql export csv "${instance}" \
    "gs://${BUCKET}/${GCS_EXPORT_PREFIX}/_schema_${table}.csv" \
    --database="${DB_NAME}" \
    --project="${PROJECT_ID}" \
    --query="SELECT COLUMN_NAME, IS_NULLABLE, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='${DB_NAME}' AND TABLE_NAME='${table}' ORDER BY ORDINAL_POSITION" \
    --quiet 2>/dev/null
  schema_csv=$(gsutil cat "gs://${BUCKET}/${GCS_EXPORT_PREFIX}/_schema_${table}.csv" 2>/dev/null)

  if [[ -z "${schema_csv}" ]]; then
    BUILT_QUERY="SELECT * FROM ${table}"
    return
  fi

  local cols=""
  local bq_schema=""
  while IFS= read -r line; do
    # Parse: "col_name","YES|NO","data_type"
    local col_name
    col_name=$(echo "${line}" | sed 's/^"\([^"]*\)".*/\1/')
    local nullable
    nullable=$(echo "${line}" | sed 's/^"[^"]*","\([^"]*\)".*/\1/')
    local dtype
    dtype=$(echo "${line}" | sed 's/^"[^"]*","[^"]*","\([^"]*\)"/\1/')

    # Map MySQL type → BQ type
    local bq_type="STRING"
    case "${dtype}" in
      int|tinyint|smallint|mediumint) bq_type="INT64" ;;
      bigint)                         bq_type="INT64" ;;
      double|float|decimal)           bq_type="FLOAT64" ;;
      date|datetime|timestamp)        bq_type="STRING" ;; # keep as string to avoid parse issues
      binary)                         bq_type="INT64" ;;
      *)                              bq_type="STRING" ;;
    esac
    bq_schema="${bq_schema}${col_name}:${bq_type},"

    if [[ "${nullable}" == "YES" ]]; then
      # Wrap in IFNULL based on data type
      case "${dtype}" in
        int|bigint|double|float|decimal|tinyint|smallint|mediumint)
          cols="${cols}IFNULL(\`${col_name}\`, 0) AS \`${col_name}\`,"
          ;;
        date|datetime|timestamp)
          cols="${cols}IFNULL(CAST(\`${col_name}\` AS CHAR), '') AS \`${col_name}\`,"
          ;;
        binary)
          cols="${cols}IFNULL(\`${col_name}\`, 0) AS \`${col_name}\`,"
          ;;
        *)
          cols="${cols}IFNULL(\`${col_name}\`, '') AS \`${col_name}\`,"
          ;;
      esac
    else
      cols="${cols}\`${col_name}\`,"
    fi
  done <<< "${schema_csv}"

  # Remove trailing commas
  cols="${cols%,}"
  bq_schema="${bq_schema%,}"

  BUILT_QUERY="SELECT ${cols} FROM ${table}"
  BUILT_SCHEMA="${bq_schema}"
}

# ── Export + Load one table ───────────────────────────────────────────
export_and_load() {
  local instance="$1"
  local table="$2"
  local GCS_CSV="gs://${BUCKET}/${GCS_EXPORT_PREFIX}/${table}.csv.gz"

  printf "[%s] %-45s schema ... " "$(ts)" "${table}"

  build_query_and_schema "${instance}" "${table}"

  printf "exporting ... "
  if ! gcloud sql export csv "${instance}" "${GCS_CSV}" \
       --database="${DB_NAME}" \
       --project="${PROJECT_ID}" \
       --offload \
       --query="${BUILT_QUERY}" \
       --quiet 2>/tmp/reexport_err_${table}.log; then
    printf "EXPORT FAIL\n"
    head -2 /tmp/reexport_err_${table}.log
    return 1
  fi

  printf "loading ... "
  local schema_flag=""
  if [[ -n "${BUILT_SCHEMA}" ]]; then
    schema_flag="${BUILT_SCHEMA}"
  fi

  if [[ -n "${schema_flag}" ]]; then
    if ! bq --project_id="${PROJECT_ID}" load \
         --source_format=CSV \
         --schema="${schema_flag}" \
         --allow_quoted_newlines \
         --replace \
         "${DATASET}.${table}" \
         "${GCS_CSV}" 2>/tmp/reexport_bqerr_${table}.log; then
      printf "BQ FAIL\n"
      head -2 /tmp/reexport_bqerr_${table}.log
      return 1
    fi
  else
    if ! bq --project_id="${PROJECT_ID}" load \
         --source_format=CSV \
         --autodetect \
         --allow_quoted_newlines \
         --replace \
         "${DATASET}.${table}" \
         "${GCS_CSV}" 2>/tmp/reexport_bqerr_${table}.log; then
      printf "BQ FAIL\n"
      head -2 /tmp/reexport_bqerr_${table}.log
      return 1
    fi
  fi

  printf "OK\n"
  return 0
}

# ── Main ──────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Re-export with IFNULL → BigQuery (NULL fix)           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if [[ "${1:-}" == "--all-from-a" ]]; then
  INSTANCE="pkg25-import"
  TABLES=(C23_BioEntities C13_Link_ClinicalTrials_BioEntities C18_Link_Patents_BioEntities C15_Patents C11_ClinicalTrials C21_Bioentity_Relationships)
else
  INSTANCE="${1:?Usage: $0 <instance> <table1> [table2...] | --all-from-a}"
  shift
  TABLES=("$@")
fi

PASS=0
FAIL=0
for table in "${TABLES[@]}"; do
  if export_and_load "${INSTANCE}" "${table}"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ${PASS} OK, ${FAIL} FAIL"
echo "════════════════════════════════════════════════════════════"
