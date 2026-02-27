#!/usr/bin/env bash
# =============================================================================
# Upload orkg_contributions.csv to GCS and load into BigQuery kg_raw dataset.
#
# Prerequisites:
#   - gcloud CLI authenticated (gcloud auth login)
#   - bq and gsutil on PATH
#
# Usage:
#   source scripts/gcp/switch-config.sh && use_multihop
#   bash scripts/gcp/load_orkg_to_bigquery.sh
# =============================================================================

set -euo pipefail

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
PROJECT_ID="multihopwanderer-1771992134"
DATASET="kg_raw"
TABLE="orkg_contributions"
BUCKET="gs://multihopwanderer-1771992134-team-bucket/processed"
LOCATION="us-central1"

LOCAL_CSV="$(cd "$(dirname "$0")/../.." && pwd)/data/processed/orkg_contributions.csv"
GCS_URI="${BUCKET}/orkg_contributions.csv"

# All columns are STRING — pipe-separated entity_ids/entity_names stay as text
SCHEMA="contribution_id:STRING,\
paper_id:STRING,\
paper_title:STRING,\
paper_doi:STRING,\
paper_year:STRING,\
venue:STRING,\
disease_problem:STRING,\
objective:STRING,\
results:STRING,\
methodology:STRING,\
risk_factors:STRING,\
treatment:STRING,\
entity_ids:STRING,\
entity_names:STRING"
# ──────────────────────────────────────────────────────────────────────────────

# ── PREREQUISITES ─────────────────────────────────────────────────────────────
for cmd in bq gsutil; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: ${cmd} not found on PATH"; exit 1; }
done

[[ -f "${LOCAL_CSV}" ]] || { echo "ERROR: CSV not found at ${LOCAL_CSV}"; exit 1; }
# ──────────────────────────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ORKG Contributions → BigQuery                          ║"
echo "║  Project : ${PROJECT_ID}                     ║"
echo "║  Table   : ${DATASET}.${TABLE}                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── STEP 1: Upload CSV to GCS ─────────────────────────────────────────────────
echo "[1/2] Uploading CSV to GCS ..."
echo "      ${LOCAL_CSV}"
echo "   -> ${GCS_URI}"
gsutil cp "${LOCAL_CSV}" "${GCS_URI}"
echo "      Upload OK  ($(gsutil du -h "${GCS_URI}" | awk '{print $1}'))"
echo ""

# ── STEP 2: Load GCS → BigQuery ───────────────────────────────────────────────
echo "[2/2] Loading into BigQuery ..."
bq --project_id="${PROJECT_ID}" load \
  --location="${LOCATION}" \
  --source_format=CSV \
  --field_delimiter="," \
  --skip_leading_rows=1 \
  --replace \
  --max_bad_records=5 \
  "${PROJECT_ID}:${DATASET}.${TABLE}" \
  "${GCS_URI}" \
  "${SCHEMA}"

echo "      Load OK"
echo ""

# ── VERIFICATION ──────────────────────────────────────────────────────────────
echo "Row count:"
bq --project_id="${PROJECT_ID}" query \
  --use_legacy_sql=false \
  --format=pretty \
  "SELECT COUNT(*) AS total_rows,
          COUNTIF(entity_ids != '') AS rows_with_entities,
          COUNT(DISTINCT paper_id) AS distinct_papers
   FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\`"

echo ""
echo "Sample (3 rows with entity matches):"
bq --project_id="${PROJECT_ID}" query \
  --use_legacy_sql=false \
  --format=pretty \
  "SELECT contribution_id, paper_year, disease_problem,
          SUBSTR(results, 0, 80) AS results_preview,
          entity_names
   FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\`
   WHERE entity_ids != ''
   LIMIT 3"

echo ""
echo "Done. Table: ${PROJECT_ID}:${DATASET}.${TABLE}"
