#!/usr/bin/env bash
# =============================================================================
# Load PKG 2.0 into BigQuery via Parquet (fast, parallel)
#
# Pipeline:
#   1. pip install pandas pyarrow (if needed)
#   2. Convert TSV.gz → Parquet files (parallel, tolerates truncated gzip)
#   3. Create BigQuery dataset kg_raw (idempotent)
#   4. Upload available Parquet files in parallel (xargs -P4)
#   5. Print summary with pass/fail/skip + row counts
#
# Usage:
#   source scripts/gcp/switch-config.sh && use_multihop
#   bash scripts/gcp/load_pkg2_to_bigquery.sh
# =============================================================================

set -uo pipefail

# ── CONFIGURATION ────────────────────────────────────────────────────────────
PROJECT_ID="multihopwanderer-1771992134"
DATASET="kg_raw"
LOCATION="us-central1"
PARALLEL_UPLOADS=4

# Resolve paths relative to repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATA_DIR="${REPO_ROOT}/data/pkg2"
PARQUET_DIR="${REPO_ROOT}/data/pkg2_parquet"
CONVERT_SCRIPT="${SCRIPT_DIR}/convert_tsv_to_parquet.py"
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

# Verify all TSV.gz files exist
MISSING=0
for table in "${TABLES[@]}"; do
  if [[ ! -f "${DATA_DIR}/${table}.tsv.gz" ]]; then
    echo "ERROR: Missing file: ${DATA_DIR}/${table}.tsv.gz"
    MISSING=$((MISSING + 1))
  fi
done
[[ "${MISSING}" -eq 0 ]] || exit 1
echo "All ${#TABLES[@]} TSV.gz files found"
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

# ── STEP 2: Convert TSV.gz → Parquet ────────────────────────────────────────
echo ""
echo "Step 2: Converting TSV.gz → Parquet (tolerating truncated gzip)..."
python3 "${CONVERT_SCRIPT}"
# Script exits 0 even on partial failure — we upload whatever was created

# Count how many parquet files were produced
PARQUET_COUNT=0
SKIPPED_TABLES=()
for table in "${TABLES[@]}"; do
  if [[ -f "${PARQUET_DIR}/${table}.parquet" ]]; then
    PARQUET_COUNT=$((PARQUET_COUNT + 1))
  else
    SKIPPED_TABLES+=("${table}")
  fi
done

if [[ "${PARQUET_COUNT}" -eq 0 ]]; then
  echo "ERROR: No Parquet files were created. Cannot proceed."
  exit 1
fi

echo "  ${PARQUET_COUNT}/${#TABLES[@]} Parquet files ready"
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
  --description="PKG 2.0 raw tables" \
  "${PROJECT_ID}:${DATASET}" 2>/dev/null || true
echo "  Dataset ready"
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 4: Parallel Parquet upload ──────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Loading PKG 2.0 → BigQuery (Parquet, ${PARALLEL_UPLOADS} parallel)     ║"
echo "║  Project: ${PROJECT_ID}                                 ║"
echo "║  Dataset: ${DATASET}                                    ║"
echo "║  Files:   ${PARQUET_COUNT} of ${#TABLES[@]}                                       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Temp dir for per-table results
RESULT_DIR="$(mktemp -d)"
trap 'rm -rf "${RESULT_DIR}"' EXIT

upload_one() {
  local parquet_file="$1"
  local table_name
  table_name="$(basename "${parquet_file}" .parquet)"
  local full_table="${PROJECT_ID}:${DATASET}.${table_name}"
  local result_file="${RESULT_DIR}/${table_name}"

  local log_file
  log_file="$(mktemp)"

  printf "[%s] Loading %-45s ... " "$(date +%H:%M:%S)" "${table_name}"

  local rc=0
  bq --project_id="${PROJECT_ID}" load \
    --source_format=PARQUET \
    --replace \
    "${full_table}" \
    "${parquet_file}" >"${log_file}" 2>&1 || rc=$?

  if [[ "$rc" -eq 0 ]]; then
    echo "OK"
    echo "PASS" > "${result_file}"
  else
    echo "FAILED"
    cat "${log_file}" >&2
    echo "FAIL" > "${result_file}"
  fi

  rm -f "${log_file}"
}
export -f upload_one
export PROJECT_ID DATASET RESULT_DIR

# Run uploads in parallel (only for files that exist)
printf '%s\n' "${PARQUET_DIR}"/*.parquet | xargs -P"${PARALLEL_UPLOADS}" -I{} bash -c 'upload_one "$@"' _ {}
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
  if [[ ! -f "${PARQUET_DIR}/${table}.parquet" ]]; then
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
