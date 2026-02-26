#!/usr/bin/env bash
# =============================================================================
# Load PKG 2.0 TSV.gz files from GCS into BigQuery dataset kg_raw
#
# Prerequisites:
#   - gcloud CLI authenticated (gcloud auth login)
#   - BigQuery API enabled on the project
#
# Usage:
#   source scripts/gcp/switch-config.sh && use_multihop
#   bash scripts/gcp/load_pkg2_to_bigquery.sh
# =============================================================================

set -uo pipefail

# ── CONFIGURATION ────────────────────────────────────────────────────────────
PROJECT_ID="multihopwanderer-1771992134"
DATASET="kg_raw"
BUCKET="gs://multihopwanderer-1771992134-team-bucket/pkg2"
LOCATION="us-central1"
RETRIES=3
# ─────────────────────────────────────────────────────────────────────────────

# ── SCHEMAS (C-prefix tables, from PKG 2.0 paper) ───────────────────────────
SCHEMA_C23="EntityId:STRING,Type:STRING,Mention:STRING"
SCHEMA_C01="PMID:INT64,PubYear:INT64,ArticleTitle:STRING,AuthorNum:INT64,CitedCount:INT64,IsClinical:INT64"
SCHEMA_C06="PMID:INT64,StartPosition:INT64,EndPosition:INT64,Mention:STRING,Entityid:STRING,Type:INT64,is_neural_normalized:INT64"
SCHEMA_C11="nct_id:STRING,brief_title:STRING,start_date:DATE"
SCHEMA_C11_FALLBACK="nct_id:STRING,brief_title:STRING,start_date:STRING"
SCHEMA_C13="nct_id:STRING,Entityid:STRING"
SCHEMA_C15="PatentId:STRING,GrantedDate:DATE,Title:STRING,Abstract:STRING"
SCHEMA_C15_FALLBACK="PatentId:STRING,GrantedDate:STRING,Title:STRING,Abstract:STRING"
SCHEMA_C18="PatentId:STRING,StartPosition:INT64,EndPosition:INT64,Mention:STRING,Entityid:STRING,Type:INT64"
SCHEMA_C21="PMID:INT64,entity_id1:STRING,entity_id2:STRING,relation_type:STRING,relation_id:STRING"
# ─────────────────────────────────────────────────────────────────────────────

# ── PREREQUISITES ────────────────────────────────────────────────────────────
for cmd in bq gsutil; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: ${cmd} not found on PATH"; exit 1; }
done

echo "Checking GCS access..."
if ! gsutil ls "${BUCKET}/" >/dev/null 2>&1; then
  echo "ERROR: Cannot list ${BUCKET}/. Check gcloud auth."
  exit 1
fi
echo "  GCS access OK"
# ─────────────────────────────────────────────────────────────────────────────

# ── CREATE DATASET ───────────────────────────────────────────────────────────
echo "Creating dataset ${PROJECT_ID}:${DATASET} (if not exists)..."
bq --project_id="${PROJECT_ID}" mk \
  --dataset \
  --location="${LOCATION}" \
  --description="PKG 2.0 raw tables loaded from GCS" \
  "${PROJECT_ID}:${DATASET}" 2>/dev/null || true
echo "  Dataset ready"
# ─────────────────────────────────────────────────────────────────────────────

# ── LOAD FUNCTION ────────────────────────────────────────────────────────────
RESULTS=()

load_table() {
  local file_name="$1"
  local table_name="$2"
  local schema="$3" # schema string or "AUTODETECT"

  local gcs_uri="${BUCKET}/${file_name}"
  local full_table="${PROJECT_ID}:${DATASET}.${table_name}"

  local log_file
  log_file="$(mktemp)"

  for attempt in $(seq 1 "${RETRIES}"); do
    printf "[%s] %-45s (%d/%d) ... " \
      "$(date +%H:%M:%S)" "${table_name}" "$attempt" "$RETRIES"

    local rc=0
    if [[ "${schema}" == "AUTODETECT" ]]; then
      bq --project_id="${PROJECT_ID}" load \
        --source_format=CSV \
        --field_delimiter=$'\t' \
        --quote="" \
        --skip_leading_rows=1 \
        --replace \
        --max_bad_records=0 \
        --autodetect \
        "${full_table}" \
        "${gcs_uri}" >"${log_file}" 2>&1 || rc=$?
    else
      bq --project_id="${PROJECT_ID}" load \
        --source_format=CSV \
        --field_delimiter=$'\t' \
        --quote="" \
        --skip_leading_rows=1 \
        --replace \
        --max_bad_records=0 \
        "${full_table}" \
        "${gcs_uri}" \
        "${schema}" >"${log_file}" 2>&1 || rc=$?
    fi

    if [[ "$rc" -eq 0 ]]; then
      echo "OK"
      RESULTS+=("PASS  ${table_name}")
      rm -f "${log_file}"
      return 0
    fi

    echo "FAILED"
    cat "${log_file}" >&2
    sleep $((attempt * 5))
  done

  rm -f "${log_file}"

  RESULTS+=("FAIL  ${table_name}")
  return 1
}
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Loading PKG 2.0 → BigQuery (${DATASET})               ║"
echo "║  Project: ${PROJECT_ID}                                 ║"
echo "║  Source:  ${BUCKET}                                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

FAILED=0

# ── C-prefix tables (explicit schemas) ──────────────────────────────────────

# Smallest file first as sanity check
load_table "C23_BioEntities.tsv.gz"      "C23_BioEntities"      "${SCHEMA_C23}" || FAILED=$((FAILED + 1))

load_table "C01_Papers.tsv.gz"           "C01_Papers"           "${SCHEMA_C01}" || FAILED=$((FAILED + 1))
load_table "C06_Link_Papers_BioEntities.tsv.gz" "C06_Link_Papers_BioEntities" "${SCHEMA_C06}" || FAILED=$((FAILED + 1))

# C11 with DATE fallback
if ! load_table "C11_ClinicalTrials.tsv.gz" "C11_ClinicalTrials" "${SCHEMA_C11}"; then
  echo "  Retrying C11 with start_date as STRING..."
  RESULTS=("${RESULTS[@]:0:${#RESULTS[@]}-1}") # pop the FAIL entry
  load_table "C11_ClinicalTrials.tsv.gz" "C11_ClinicalTrials" "${SCHEMA_C11_FALLBACK}" || FAILED=$((FAILED + 1))
fi

load_table "C13_Link_ClinicalTrials_BioEntities.tsv.gz" "C13_Link_ClinicalTrials_BioEntities" "${SCHEMA_C13}" || FAILED=$((FAILED + 1))

# C15 with DATE fallback
if ! load_table "C15_Patents.tsv.gz" "C15_Patents" "${SCHEMA_C15}"; then
  echo "  Retrying C15 with GrantedDate as STRING..."
  RESULTS=("${RESULTS[@]:0:${#RESULTS[@]}-1}")
  load_table "C15_Patents.tsv.gz" "C15_Patents" "${SCHEMA_C15_FALLBACK}" || FAILED=$((FAILED + 1))
fi

load_table "C18_Link_Patents_BioEntities.tsv.gz" "C18_Link_Patents_BioEntities" "${SCHEMA_C18}" || FAILED=$((FAILED + 1))
load_table "C21_Bioentity_Relationships.tsv.gz"  "C21_Bioentity_Relationships"  "${SCHEMA_C21}" || FAILED=$((FAILED + 1))

# ── A-prefix tables (autodetect) ────────────────────────────────────────────

load_table "A01_Articles.tsv.gz"         "A01_Articles"         "AUTODETECT" || FAILED=$((FAILED + 1))
load_table "A03_KeywordList.tsv.gz"      "A03_KeywordList"      "AUTODETECT" || FAILED=$((FAILED + 1))
load_table "A04_Abstract.tsv.gz"         "A04_Abstract"         "AUTODETECT" || FAILED=$((FAILED + 1))
load_table "A06_MeshHeadingList.tsv.gz"  "A06_MeshHeadingList"  "AUTODETECT" || FAILED=$((FAILED + 1))

# ── VERIFICATION ─────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Load Summary"
echo "════════════════════════════════════════════════════════════"
for r in "${RESULTS[@]}"; do
  echo "  ${r}"
done
echo "════════════════════════════════════════════════════════════"
echo "  Total: ${#RESULTS[@]} tables, ${FAILED} failures"
echo "════════════════════════════════════════════════════════════"

if [[ "${FAILED}" -gt 0 ]]; then
  echo ""
  echo "Re-run the script to retry failed tables (--replace is idempotent)."
  exit 1
fi

echo ""
echo "=== Row counts ==="
for table in C23_BioEntities C01_Papers C06_Link_Papers_BioEntities \
             C11_ClinicalTrials C13_Link_ClinicalTrials_BioEntities \
             C15_Patents C18_Link_Patents_BioEntities \
             C21_Bioentity_Relationships A01_Articles A03_KeywordList \
             A04_Abstract A06_MeshHeadingList; do
  count=$(bq --project_id="${PROJECT_ID}" query \
    --use_legacy_sql=false \
    --format=csv \
    --quiet \
    "SELECT COUNT(*) AS cnt FROM \`${PROJECT_ID}.${DATASET}.${table}\`" 2>/dev/null \
    | tail -1)
  printf "  %-45s %s rows\n" "${table}" "${count}"
done

echo ""
echo "All 12 tables loaded into ${PROJECT_ID}:${DATASET}"
