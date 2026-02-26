# PKG2 Evidence Data Exploration Findings

Date: 2026-02-26  
Scope: Download and inspect PubMed/clinical-trial/patent evidence files for link explanation quality.  
Constraint honored: **No BigQuery table changes**.

## Files downloaded and inspected

From `gs://multihopwanderer-1771992134-team-bucket/pkg2/`:

- `A04_Abstract.tsv.gz` (105.89 MiB)
- `C06_Link_Papers_BioEntities.tsv.gz` (206.75 MiB)
- `C11_ClinicalTrials.tsv.gz` (207.36 MiB)
- `C13_Link_ClinicalTrials_BioEntities.tsv.gz` (161.87 MiB)
- `C15_Patents.tsv.gz` (103.75 MiB)
- `C18_Link_Patents_BioEntities.tsv.gz` (105.72 MiB)

Local download path used for exploration: `/tmp/pkg2_evidence`.

## Critical data quality finding

`gzip -t` integrity check:

- Fails (`unexpected end of file`): `A04`, `C06`, `C11`, `C15`, `C18`
- Passes: `C13`

This indicates likely truncated/corrupted gzip streams in source objects (local file sizes match remote object sizes).  
Impact: parsing succeeds for large readable portions, but completeness is uncertain.

## Structure summary

### Metadata/evidence text tables

- `A04_Abstract` columns: `id, PMID, AbstractText, ...` (5 columns)
- `C11_ClinicalTrials` columns include rich trial text:
  - `nct_id`, `brief_title`, `brief_summaries`, `detailed_descriptions`, `conditions` (18 columns)
- `C15_Patents` columns include:
  - `PatentId`, `Title`, `Abstract`, granted metadata/flags (13 columns)

### Entity-link tables

- `C06_Link_Papers_BioEntities`: paper PMID -> extracted entities (17 columns)
- `C13_Link_ClinicalTrials_BioEntities`: NCT -> extracted entities (16 columns)
- `C18_Link_Patents_BioEntities`: PatentId -> extracted entities (16 columns)

Entity typing exists (`Type`) and normalized-like ID fields exist (`mesh`, `NCBIGene`, `CHEBI`, `EntityId`).

## Readable-row counts (from decompressed readable content)

- `A04_Abstract`: 363,535 lines
- `C06_Link_Papers_BioEntities`: 7,748,838 lines
- `C11_ClinicalTrials`: 275,223 lines
- `C13_Link_ClinicalTrials_BioEntities`: 6,887,447 lines
- `C15_Patents`: 526,443 lines
- `C18_Link_Patents_BioEntities`: 4,349,719 lines

## Coverage and joinability signals

Unique IDs observed:

- PMIDs in abstracts: 362,083
- PMIDs in paper-entity links: 1,012,965
- NCT IDs in trials: 275,223
- NCT IDs in trial-entity links: 472,636
- Patent IDs in patents: 526,443
- Patent IDs in patent-entity links: 689,454

Overlap between metadata and entity-link IDs:

- PMID overlap: 351,283
- NCT overlap: 243,367
- Patent overlap: 359,124

IDs in link tables but missing in metadata tables:

- NCT missing from trial metadata: 229,269
- PatentId missing from patent metadata: 330,330

Interpretation:

- The schema is suitable for evidence linking.
- Current objects appear incomplete/inconsistent across metadata vs link tables (likely worsened by gzip integrity issues).

## Entity type distribution (top)

- Papers (`C06`): drug, disease, species, gene, cell_type, DNA, cell_line
- Trials (`C13`): disease, species, drug, gene, cell_type, DNA
- Patents (`C18`): drug, DNA, gene, disease, species, cell_type

This is strong for building explanation bundles by biomedical entity overlap.

## What this enables for the app right now

You can provide better edge explanations without changing PrimeKG itself:

1. For each PrimeKG edge `(x,y)`, map to canonical IDs (`NCBIGene`, `CHEBI`, `MESH`, etc.).
2. Retrieve top evidence from:
   - papers (PMID + abstract snippet),
   - trials (NCT + summary/description snippet),
   - patents (PatentId + abstract snippet),
   by matching linked entities against edge endpoints.
3. Return `top-k evidence bundle` per edge with:
   - source type (`paper|trial|patent`),
   - source ID,
   - short snippet,
   - score (match count + source diversity + recency).

This directly supports challenge requirements: transparent path traversal + citations/snippets per connection.

## Recommended immediate next steps

1. Re-upload or regenerate corrupted gzip files (`A04`, `C06`, `C11`, `C15`, `C18`) and validate with `gzip -t` before ingestion.
2. Build a lightweight normalization pipeline (outside serving path first):
   - canonical entity IDs
   - evidence-doc registry (`PMID/NCT/PatentId`)
   - edge-to-evidence mapping table.
3. Add API contract for explanation payload:
   - `edge_id`, `claim`, `evidence[]`, `citations[]`, `path_context`.
4. Keep Gemini constrained to returned snippets/IDs to avoid ungrounded reasoning.

## Feasibility assessment

High.  
Even with current files, the structure is sufficient to materially improve explanations.  
Main blocker is data integrity/completeness of several gzip sources, not model capability.
