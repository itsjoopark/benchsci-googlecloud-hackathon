#!/usr/bin/env bash
# =============================================================================
# Download PKG 2.0 tables for Challenge 5: "From Wandering to Wisdom"
# Interactive multi-hop biomedical knowledge graph explorer
#
# Designed to run directly in Google Cloud Shell (gcloud/gsutil pre-installed)
#
# Usage:
#   1. Open Google Cloud Shell: https://shell.cloud.google.com
#   2. Set your bucket:  export GCS_BUCKET=gs://YOUR-BUCKET-NAME/pkg2
#   3. Run:  bash download_challenge5.sh
#
# Or inline:
#   GCS_BUCKET=gs://my-bucket/pkg2 bash download_challenge5.sh
# =============================================================================

set -euo pipefail

# ── CONFIGURATION ────────────────────────────────────────────────────────────
: "${GCS_BUCKET:?ERROR: Set GCS_BUCKET first, e.g. export GCS_BUCKET=gs://my-bucket/pkg2}"
PARALLEL=4
RETRIES=3
# ─────────────────────────────────────────────────────────────────────────────

BASE="https://download.scidb.cn/download"

# Format: "fileId|path|fileName"
# Using PKG24S4 TSV files (latest version, fastest to load into BigQuery)
declare -a FILES=(
  # ── CRITICAL: Graph nodes & edges ──────────────────────────────────────
  # BioEntities (nodes: genes, diseases, drugs, proteins, pathways)
  "c2e67faae933f6f53d3ef13ef968bb59|C23_BioEntities.tsv.gz"
  # Bioentity relationships (edges: the core of multi-hop traversal)
  "588c06e634fbc2a489a32aa0755d0abe|C21_Bioentity_Relationships.tsv.gz"
  # Paper ↔ BioEntity links (evidence backing each edge, 482M linkages)
  "e47696ed322799ea032394fd3b264505|C06_Link_Papers_BioEntities.tsv.gz"

  # ── CRITICAL: Paper context ────────────────────────────────────────────
  # Article metadata (titles, PMIDs, dates)
  "045e3465e929b40b05b8975fe9442bb9|A01_Articles.tsv.gz"
  # Abstracts (for summarization when user explores a relationship)
  "652997345c48ecacf980acea26c6aa2a|A04_Abstract.tsv.gz"
  # MeSH headings (disease/therapeutic area filtering)
  "22b5d8ac0ae2fc4bafe2eafd678c085b|A06_MeshHeadingList.tsv.gz"

  # ── HIGH VALUE: Richer exploration ─────────────────────────────────────
  # Enriched paper data from C-module (DOIs, citation counts)
  "996223d910b3b6c001ca059c690f0274|C01_Papers.tsv.gz"
  # Clinical trials (translational relevance along multi-hop paths)
  "b89d7fe224363c1c0a135feca24b18fa|C11_ClinicalTrials.tsv.gz"
  # Clinical trial ↔ BioEntity links
  "d26aae2a413a5d02c43d4f6f1dd3c825|C13_Link_ClinicalTrials_BioEntities.tsv.gz"
  # Patents (commercial/IP signal along paths)
  "045a656506675cd0dd3a58d7114918b7|C15_Patents.tsv.gz"
  # Patent ↔ BioEntity links
  "9fd7b8f01cbda24cbd3593769845caa2|C18_Link_Patents_BioEntities.tsv.gz"
  # Keywords (search/filtering entry points into the graph)
  "6db2ad18f5bec998483a2f89d5b0a7b3|A03_KeywordList.tsv.gz"
)

# ── Download function ────────────────────────────────────────────────────────
download_one() {
  local entry="$1"
  local file_id="${entry%%|*}"
  local file_name="${entry##*|}"
  local url="${BASE}?fileId=${file_id}&fileName=${file_name}"
  local dest="${GCS_BUCKET}/${file_name}"

  for attempt in $(seq 1 "$RETRIES"); do
    printf "[%s] (%d/%d) %s ... " "$(date +%H:%M:%S)" "$attempt" "$RETRIES" "$file_name"
    if curl -sS -L --fail --retry 2 --retry-delay 5 --connect-timeout 30 "$url" \
        | gsutil -q cp - "$dest" 2>/dev/null; then
      echo "✓"
      return 0
    fi
    echo "✗ retrying"
    sleep $((attempt * 3))
  done

  echo "✗✗ FAILED: ${file_name}"
  return 1
}
export -f download_one
export BASE GCS_BUCKET RETRIES

# ── Main ─────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Challenge 5: From Wandering to Wisdom                  ║"
echo "║  PKG 2.0 → GCS (streaming, no local disk)              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Bucket:  ${GCS_BUCKET}"
echo "║  Files:   ${#FILES[@]}"
echo "║  Parallel: ${PARALLEL}"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

FAILED=0
printf '%s\n' "${FILES[@]}" | xargs -P "$PARALLEL" -I{} bash -c 'download_one "{}"' || FAILED=1

echo ""
echo "────────────────────────────────────────────────────────────"
if [ "$FAILED" -eq 0 ]; then
  echo "✓ All ${#FILES[@]} files transferred to ${GCS_BUCKET}"
  echo ""
  echo "Verify with:  gsutil ls -lh ${GCS_BUCKET}/"
else
  echo "⚠ Some transfers failed. Re-run the script to retry."
fi
echo "────────────────────────────────────────────────────────────"
