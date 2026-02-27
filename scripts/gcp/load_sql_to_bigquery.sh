#!/usr/bin/env bash
# =============================================================================
# Load MySQL dump (.sql.gz) → BigQuery via Parquet (streaming, parallel)
#
# Pipeline:
#   1. pip install pandas pyarrow (if needed)
#   2. Convert .sql.gz → sharded Parquet files (parallel + sequential for large)
#   3. Create BigQuery dataset pubmed_kg (idempotent)
#   4. Upload Parquet shards in parallel (xargs -P4, table-level parallelism)
#   5. Print summary with pass/fail/skip + row counts
#
# Usage:
#   source scripts/gcp/switch-config.sh && use_multihop
#   bash scripts/gcp/load_sql_to_bigquery.sh
# =============================================================================

set -uo pipefail

# ── CONFIGURATION ────────────────────────────────────────────────────────────
PROJECT_ID="multihopwanderer-1771992134"
DATASET="pubmed_kg"
LOCATION="us-central1"
PARALLEL_UPLOADS=4

# Resolve paths relative to repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATA_DIR="${REPO_ROOT}/data/pkg2_sql"
PARQUET_DIR="${REPO_ROOT}/data/pkg2_sql_parquet"
CONVERT_SCRIPT="${SCRIPT_DIR}/convert_sql_to_parquet.py"
# ─────────────────────────────────────────────────────────────────────────────

# All 12 PKG 2.0 tables
TABLES=(
  C23_BioEntities
  C13_Link_ClinicalTrials_BioEntities
  C21_Bioentity_Relationships
  C18_Link_Patents_BioEntities
  C15_Patents
  C06_Link_Papers_BioEntities
  C11_ClinicalTrials
  C01_Papers
  A04_Abstract
  A06_MeshHeadingList
  A01_Articles
  A03_KeywordList
)

# ── PREREQUISITES ────────────────────────────────────────────────────────────
command -v bq >/dev/null 2>&1 || { echo "ERROR: bq not found on PATH"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found on PATH"; exit 1; }

if [[ ! -d "${DATA_DIR}" ]]; then
  echo "ERROR: Data directory not found: ${DATA_DIR}"
  exit 1
fi

# Verify all .sql.gz files exist
MISSING=0
for table in "${TABLES[@]}"; do
  if [[ ! -f "${DATA_DIR}/${table}.sql.gz" ]]; then
    echo "ERROR: Missing file: ${DATA_DIR}/${table}.sql.gz"
    MISSING=$((MISSING + 1))
  fi
done
[[ "${MISSING}" -eq 0 ]] || exit 1
echo "All ${#TABLES[@]} .sql.gz files found"
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 1: Install Python deps ─────────────────────────────────────────────
echo ""
echo "Step 1: Ensuring pandas + pyarrow are installed..."
python3 -m pip install --quiet pandas pyarrow || {
  echo "ERROR: Failed to install pandas/pyarrow. Try: python3 -m pip install pandas pyarrow"
  exit 1
}
echo "  Dependencies ready"
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 2: Convert .sql.gz → Parquet ────────────────────────────────────────
echo ""
echo "Step 2: Converting .sql.gz → sharded Parquet..."
python3 "${CONVERT_SCRIPT}"
# Script exits 0 even on partial failure — we upload whatever was created

# Discover which tables produced shards
AVAILABLE_TABLES=()
SKIPPED_TABLES=()
for table in "${TABLES[@]}"; do
  # Check if at least one shard exists (TableName_000.parquet)
  if ls "${PARQUET_DIR}/${table}_"*.parquet >/dev/null 2>&1; then
    AVAILABLE_TABLES+=("${table}")
  else
    SKIPPED_TABLES+=("${table}")
  fi
done

if [[ "${#AVAILABLE_TABLES[@]}" -eq 0 ]]; then
  echo "ERROR: No Parquet shards were created. Cannot proceed."
  exit 1
fi

echo "  ${#AVAILABLE_TABLES[@]}/${#TABLES[@]} tables have Parquet shards"
if [[ ${#SKIPPED_TABLES[@]} -gt 0 ]]; then
  echo "  Skipped (conversion failed): ${SKIPPED_TABLES[*]}"
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 3: Create BigQuery dataset ─────────────────────────────────────────
echo ""
echo "Step 3: Creating dataset ${PROJECT_ID}:${DATASET} (if not exists)..."
bq --project_id="${PROJECT_ID}" mk \
  --dataset \
  --location="${LOCATION}" \
  --description="PKG 2.0 PubMed knowledge graph (from MySQL dumps)" \
  "${PROJECT_ID}:${DATASET}" 2>/dev/null || true
echo "  Dataset ready"
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 4: Parallel Parquet upload ──────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Loading SQL dump → BigQuery (Parquet, ${PARALLEL_UPLOADS} parallel)    ║"
echo "║  Project: ${PROJECT_ID}                                 ║"
echo "║  Dataset: ${DATASET}                                    ║"
echo "║  Tables:  ${#AVAILABLE_TABLES[@]} of ${#TABLES[@]}                                       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Temp dir for per-table results
RESULT_DIR="$(mktemp -d)"
trap 'rm -rf "${RESULT_DIR}"' EXIT

upload_table() {
  local table_name="$1"
  local full_table="${PROJECT_ID}:${DATASET}.${table_name}"
  local result_file="${RESULT_DIR}/${table_name}"

  # Collect all shards for this table, sorted
  local shards=()
  while IFS= read -r f; do
    shards+=("$f")
  done < <(ls "${PARQUET_DIR}/${table_name}_"*.parquet 2>/dev/null | sort)

  if [[ ${#shards[@]} -eq 0 ]]; then
    echo "FAIL" > "${result_file}"
    printf "[%s] %-45s NO SHARDS\n" "$(date +%H:%M:%S)" "${table_name}"
    return
  fi

  printf "[%s] Loading %-45s (%d shards) ... " "$(date +%H:%M:%S)" "${table_name}" "${#shards[@]}"

  local log_file
  log_file="$(mktemp)"
  local rc=0

  # First shard: --replace (creates/replaces the table)
  bq --project_id="${PROJECT_ID}" load \
    --source_format=PARQUET \
    --replace \
    "${full_table}" \
    "${shards[0]}" >"${log_file}" 2>&1 || rc=$?

  if [[ "$rc" -ne 0 ]]; then
    echo "FAILED (shard 0)"
    cat "${log_file}" >&2
    echo "FAIL" > "${result_file}"
    rm -f "${log_file}"
    return
  fi

  # Remaining shards: append
  local shard_num=1
  for shard in "${shards[@]:1}"; do
    bq --project_id="${PROJECT_ID}" load \
      --source_format=PARQUET \
      --noreplace \
      "${full_table}" \
      "${shard}" >"${log_file}" 2>&1 || rc=$?

    if [[ "$rc" -ne 0 ]]; then
      echo "FAILED (shard ${shard_num})"
      cat "${log_file}" >&2
      echo "FAIL" > "${result_file}"
      rm -f "${log_file}"
      return
    fi
    shard_num=$((shard_num + 1))
  done

  echo "OK (${#shards[@]} shards)"
  echo "PASS" > "${result_file}"
  rm -f "${log_file}"
}
export -f upload_table
export PROJECT_ID DATASET PARQUET_DIR RESULT_DIR

# Run table uploads in parallel
printf '%s\n' "${AVAILABLE_TABLES[@]}" | xargs -P"${PARALLEL_UPLOADS}" -I{} bash -c 'upload_table "$@"' _ {}
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 5: Summary ─────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Load Summary"
echo "════════════════════════════════════════════════════════════"

UPLOADED=0
UPLOAD_FAILED=0
CONVERT_SKIPPED=0
for table in "${TABLES[@]}"; do
  result_file="${RESULT_DIR}/${table}"
  if ! ls "${PARQUET_DIR}/${table}_"*.parquet >/dev/null 2>&1; then
    echo "  SKIP  ${table}  (conversion failed)"
    CONVERT_SKIPPED=$((CONVERT_SKIPPED + 1))
  elif [[ -f "${result_file}" ]] && [[ "$(cat "${result_file}")" == "PASS" ]]; then
    echo "  PASS  ${table}"
    UPLOADED=$((UPLOADED + 1))
  else
    echo "  FAIL  ${table}  (upload failed)"
    UPLOAD_FAILED=$((UPLOAD_FAILED + 1))
  fi
done

echo "════════════════════════════════════════════════════════════"
echo "  Uploaded: ${UPLOADED} | Upload failed: ${UPLOAD_FAILED} | Skipped: ${CONVERT_SKIPPED}"
echo "════════════════════════════════════════════════════════════"

# Row counts for successfully uploaded tables
if [[ "${UPLOADED}" -gt 0 ]]; then
  echo ""
  echo "=== Row counts ==="
  for table in "${TABLES[@]}"; do
    result_file="${RESULT_DIR}/${table}"
    if [[ -f "${result_file}" ]] && [[ "$(cat "${result_file}")" == "PASS" ]]; then
      count=$(bq --project_id="${PROJECT_ID}" query \
        --use_legacy_sql=false \
        --format=csv \
        --quiet \
        "SELECT COUNT(*) AS cnt FROM \`${PROJECT_ID}.${DATASET}.${table}\`" 2>/dev/null \
        | tail -1)
      printf "  %-45s %s rows\n" "${table}" "${count}"
    fi
  done
fi

echo ""
echo "Done. ${UPLOADED}/${#TABLES[@]} tables loaded into ${PROJECT_ID}:${DATASET}"
