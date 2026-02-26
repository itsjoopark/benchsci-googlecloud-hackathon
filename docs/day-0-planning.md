# Day 0 Planning (Updated)

**Date:** Feb 26, 2026  
**Hackathon:** BenchSci Challenge #5 - From Wandering to Wisdom

## Working Scope for MVP

We are prioritizing two datasets first:

- **PrimeKG** (`gs://multihopwanderer-1771992134-team-bucket/primekg.csv`)
- **PubMed-derived PKG2 extracts**
  - `pkg2/A01_Articles.tsv.gz`
  - `pkg2/A04_Abstract.tsv.gz`
  - `pkg2/C06_Link_Papers_BioEntities.tsv.gz`
  - `pkg2/C21_Bioentity_Relationships.tsv.gz`
  - `pkg2/C23_BioEntities.tsv.gz`

Goal: create a graph-serving data layer in BigQuery that supports fast 1-hop/2-hop exploration with evidence.

## Product Shape

Three-pane app:

- Left: search + entity summary
- Center: graph neighborhood
- Right: edge evidence + rationale

Core API behavior:

- `GET /search?q=...`
- `GET /neighbors/{node_id}`
- `GET /edge/{edge_id}/evidence`

## Why PrimeKG + PubMed First

- PrimeKG gives broad biomedical relationships quickly (`x_id`, `y_id`, relation, types).
- PubMed/PKG2 gives evidence grounding (`PMID`, abstracts, entity mentions/links).
- Together they satisfy both graph traversal and explainability requirements.

## BigQuery Architecture (MVP)

Datasets:

- `kg_raw` for raw external/load tables from GCS
- `kg_norm` for normalized per-source tables
- `kg_graph` for graph-serving nodes/edges/evidence

Serving tables:

- `kg_graph.nodes(node_id, node_type, display_name, aliases, xrefs)`
- `kg_graph.edges(edge_id, src_node_id, dst_node_id, predicate, source_dataset, confidence_score, evidence_count, pmids, provenance_type)`
- `kg_graph.evidence(edge_id, pmid, snippet, pub_year, source_dataset)`

Performance strategy:

- Cluster `edges` by `src_node_id, predicate, source_dataset`
- Cluster `evidence` by `edge_id, pmid`
- Precompute ranked neighbors (`neighbor_rank`) for low-latency graph expansion

## Normalization Rules

Canonical node IDs:

- Genes/proteins from PrimeKG: `NCBIGene:<id>` when `x_source/y_source = NCBI`
- Diseases from MeSH in PKG2: `MESH:<id>`
- Chemicals from ChEBI in PKG2: `CHEBI:<id>`
- Evidence documents: `PMID:<id>`

Important: keep raw IDs alongside canonical IDs for traceability.

## Day 0 Execution Plan

1. Confirm GCS access and sample records for PrimeKG + PKG2 (done).
2. Create BigQuery raw tables (or external tables) for PrimeKG and PKG2 artifacts.
3. Build normalized node/edge/evidence staging tables in `kg_norm`.
4. Build graph-serving tables in `kg_graph`.
5. Validate BRCA1 and Imatinib neighborhoods with evidence links.

## Acceptance Criteria

- Query a seed node and return ranked neighbors in <2s for typical demo requests.
- Every shown edge can return at least one evidence record when available.
- Node IDs are stable/canonical across queries.
- BRCA1 and Imatinib paths are reproducible for demo.

## Risks

- Mixed identifier namespaces require explicit ID maps.
- PubMed-scale files are large; avoid scanning raw XML for interactive requests.
- Missing project IAM for some admin operations; keep work in the project where write permissions are confirmed.

## Immediate Next Tasks

- Implement BigQuery SQL for PrimeKG + PKG2 normalization.
- Add a lightweight API query layer on top of `kg_graph`.
- Cache hot neighborhoods for demo reliability.
