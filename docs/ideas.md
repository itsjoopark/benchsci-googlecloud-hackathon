# Ideas (Updated): PrimeKG + PubMed Knowledge Graph

## Core hypothesis

A useful exploration graph needs both:

- **structural relationships** (PrimeKG)
- **evidence provenance** (PubMed/PKG2 via PMID + abstracts + linked entities)

Neither alone is enough for trustable multi-hop exploration.

## Entity model

Primary node types for MVP:

- `gene/protein`
- `disease`
- `drug`
- `pathway` (from later datasets)
- `paper` (PMID evidence node)

## Edge model

Every edge should carry:

- `predicate` (`ppi`, `drug_disease`, `gene_disease`, etc.)
- `source_dataset` (`primekg`, `pkg2`)
- `confidence_score` (if present)
- `evidence_count`
- `pmids[]` when available

## User interaction ideas

- Search by symbol/name/ID and normalize to canonical node ID.
- Show top-k neighbors with filters:
  - relation type
  - evidence-backed only
  - source dataset
- Clicking an edge opens:
  - PMIDs
  - abstract snippet
  - mention spans / linked entities

## Normalization ideas

Canonical ID strategy:

- genes/proteins: `NCBIGene:<id>` (from PrimeKG NCBI source)
- chemicals: `CHEBI:<id>` where available
- diseases: `MESH:<id>` where available
- papers: `PMID:<id>`

Supporting maps:

- `name_norm -> canonical_id`
- `source_id + source_namespace -> canonical_id`

## Query ideas for graph UX

- 1-hop query:
  - fast lookup on `src_node_id`
  - return neighbor metadata + top evidence stats
- 2-hop query:
  - expand from selected first-hop neighbors only
  - cap fanout to avoid hairball
- evidence query:
  - fetch `kg_graph.evidence` by `edge_id`

## Ranking ideas

Edge ranking score (initial heuristic):

- `w1 * normalized_confidence`
- `+ w2 * log(1 + evidence_count)`
- `+ w3 * source_priority` (curated > text-mined)

## Demo-focused outputs

- BRCA1 neighborhood with evidence-backed disease and drug connections.
- Imatinib neighborhood showing known target and downstream disease relevance.
- Path explanation assembled only from retrieved evidence rows.

## Non-goals for MVP

- Full graph DB migration before hackathon demo.
- Full PubMed baseline XML parsing in serving path.
- Complex ontology reconciliation beyond required demo entities.
