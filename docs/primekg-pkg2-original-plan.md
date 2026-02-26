# PrimeKG + PKG2 Original Execution Plan

Date: 2026-02-26  
Project: `multihopwanderer-1771992134`  
Data policy for now: use the available data in its current state.

## 1) Problem and objective

Build an interactive biomedical graph exploration system that lets scientists:

- search biomedical entities,
- explore 1-hop neighbors and 2-3 hop chains,
- inspect evidence for every shown connection,
- retrace and export reasoning paths with citations.

The system must prioritize transparent traversal over black-box ranking.

## 2) Datasets in scope

Primary graph structure:

- `multihopwanderer.primekg` in BigQuery

Evidence and explanatory context (PKG2 files in GCS):

- papers: abstracts and paper-entity links
- clinical trials: trial metadata/descriptions and trial-entity links
- patents: patent metadata/abstracts and patent-entity links
- bioentity-to-bioentity links

## 3) Product baseline (must ship)

### Core graph UX

- Entity search (gene, disease, drug, pathway, protein)
- 1-hop neighborhood visualization
- click-to-expand for 2-3 hops
- path tracker panel showing full chain

### Evidence UX

- each edge shows a top-k evidence bundle:
  - papers (PMID + snippet),
  - trials (NCT + snippet),
  - patents (PatentId + snippet)
- source badges and citation counts per edge
- citation panel with direct IDs and snippets for verification

### Baseline API shape

- `GET /search?q=...`
- `GET /neighbors/{node_id}?k=&filters=...`
- `GET /edge/{edge_id}/evidence?k=&types=paper,trial,patent`
- `GET /path/{path_id}`
- `POST /path/export`

## 4) Data model and normalization

Canonical ID model:

- genes/proteins: `NCBIGene:<id>` when source supports it
- diseases: `MESH:<id>` / `MONDO:<id>`
- chemicals/drugs: `CHEBI:<id>` / `DrugBank:<id>`
- evidence docs:
  - papers: `PMID:<id>`
  - trials: `NCT:<id>`
  - patents: `PATENT:<id>`

Graph-serving tables:

- `kg_graph.nodes`
- `kg_graph.edges`
- `kg_graph.evidence_docs`
- `kg_graph.edge_evidence_links`
- `kg_app.edge_top_evidence`

## 5) Baseline metapaths (deterministic)

Initial metapath templates to support immediately:

1. `gene -> disease`
2. `gene -> protein -> pathway`
3. `gene -> pathway -> disease`
4. `drug -> protein -> disease`
5. `drug -> disease`
6. `disease -> gene -> drug`
7. `gene -> gene -> disease`
8. `drug -> protein -> pathway -> disease`

Rules:

- max depth: 3 for interactive UI
- no cycles in one expansion request
- bounded fanout per hop
- rank by evidence strength + source diversity + recency

## 6) Future learned metapaths (after baseline)

After deterministic metapaths are stable, add learned ranking:

- candidate generation remains deterministic from graph constraints
- learning layer reranks path candidates from user feedback and evidence features

Learning signals:

- edge/path clicks,
- path save/export,
- evidence drill-down rate,
- acceptance/rejection actions.

Output remains grounded:

- model may rerank, but cannot invent nodes/edges or uncited claims.

## 7) Explanation strategy (Gemini grounded mode)

Gemini is used to summarize, not to fabricate:

- input: retrieved edge evidence bundle only
- output: short explanation + explicit citations (PMID/NCT/PatentId)
- hard rule: every claim must map to provided snippets/IDs

## 8) Meeting challenge requirements

### Core and minimum

- search + 1-hop + 2-3 hop: covered by graph API + UI traversal
- evidence per edge: covered by `edge_evidence_links` + top-k evidence bundle
- path tracking: covered by path state + path view
- BRCA1 end-to-end scenario: handled by baseline metapaths and evidence lookup

### Competitive targets to include

1. multi-entity view (`gene -> pathway -> drug -> disease`)
2. evidence strength/recency filters
3. second scenario (Imatinib)
4. full path summary with aggregated citations

## 9) Shareable reproducibility

Exported path artifact must include:

- ordered nodes and edges,
- edge predicates and scores,
- cited evidence IDs and snippets,
- dataset/model versions,
- timestamp and query context.

Formats:

- canonical JSON for replay
- Markdown summary for humans

## 10) Delivery sequence

1. Normalize PrimeKG entities and edge identifiers.
2. Build evidence-doc tables from PKG2 paper/trial/patent files.
3. Build edge-to-evidence linking and top-k ranking.
4. Implement neighbor/evidence/path APIs.
5. Wire graph UI expansion + path tracker + citation panel.
6. Add Gemini grounded summarization on clicked edge/path.
7. Add path export (JSON + Markdown).
8. Add learned reranking phase (post-baseline).
