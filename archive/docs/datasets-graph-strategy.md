# Dataset Integration Strategy for Multi-Hop Graph Explorer

## Goal

Build a queryable biomedical graph that supports fast interactive expansion:

- seed entity lookup
- 1-hop neighbor retrieval
- click-to-expand to 2+ hops
- edge-level evidence/provenance for UI panel

## Current Data Landscape (Observed)

### Buckets

- `gs://benchspark-data-1771447466-datasets` (large curated public datasets)
- `gs://multihopwanderer-1771992134-team-bucket` (team workspace; includes `primekg.csv`, `pkg2/`, BRCA1 associations)

### Key files inspected

- Reactome:
  - `reactome/NCBI2Reactome_All_Levels.txt`
  - `reactome/ReactomePathways.txt`
  - `reactome/ReactomePathwaysRelation.txt`
  - `reactome/UniProt2Reactome_All_Levels.txt`
- STRING:
  - `string/9606.protein.links.v12.0.txt.gz`
  - `string/9606.protein.aliases.v12.0.txt.gz`
- Team bucket:
  - `primekg.csv`
  - `pkg2/C23_BioEntities.tsv.gz`
  - `pkg2/C21_Bioentity_Relationships.tsv.gz`
  - `pkg2/C06_Link_Papers_BioEntities.tsv.gz`
  - `BRCA1_disease_associations.csv`

## High-Level Structure by Dataset

| Dataset | Shape | Example identifiers seen | Primary value to graph |
|---|---|---|---|
| Reactome | Mapping + hierarchy tables | Entrez Gene ID, Reactome stable IDs (`R-HSA-*`), UniProt IDs | Gene/protein-to-pathway edges, pathway hierarchy |
| STRING | PPI edge list + alias mapping | STRING protein IDs (`9606.ENSP...`), Entrez aliases | Dense protein interaction network + ID bridge |
| PrimeKG | Unified edge CSV | `x_id`, `y_id`, `x_type`, `y_type`, `x_source/y_source` (sample mostly `NCBI`) | Multi-entity edges and relation labels |
| PKG2 | Entity table + relationship table + paper/entity links | `EntityId` prefixes (`CHEBI*`, `meshD*`), `PMID`, NCBI/CHEBI columns | Literature-grounded edges and evidence anchors |
| BRCA1 associations | Gene-disease table | ENSG (`ENSG00000012048`), gene symbol, disease name, score | Seed demo edges for BRCA1 |
| ChEMBL (BigQuery) | Relational pharma schema | ChEMBL IDs, target IDs, mechanism fields | Drug-target and mechanism edges |
| DisGeNET / Open Targets | Association records | Gene IDs (NCBI or ENSG depending source), disease IDs/scores | Gene-disease edges with confidence |

## Shared Fields and Joinability

### Strong overlap

- `PMID` appears in PKG2 link/relationship files and can anchor evidence.
- Gene-centric IDs are common, but namespaces vary (`NCBI Entrez`, `ENSG`, `UniProt`, STRING protein IDs).
- Disease/chemical IDs use mixed namespaces (MeSH, MIM, ChEBI, free text names).

### Practical join bridges

- Reactome `NCBI2Reactome` uses Entrez Gene IDs directly.
- STRING aliases contain Entrez aliases (`source` includes Entrez mapping), enabling STRING -> Entrez bridge.
- BRCA1 file currently uses ENSG, so ENSG -> Entrez bridge is required to join with Reactome/DisGeNET-first pipelines.
- PKG2 has both normalized ID columns and mentions; use ID columns (`EntityId`, `mesh`, `NCBIGene`, `CHEBI`) first, mentions second.

## Normalization Requirements

Yes, normalization is required for reliable cross-dataset joins.

### Recommended canonical ID policy

- Gene: canonical `NCBIGene:<entrez_id>`
- Protein: canonical `UniProtKB:<accession>`
- Pathway: canonical `Reactome:<stable_id>`
- Disease: canonical `MESH:<id>` or `DOID:<id>` when available
- Drug/Chemical: canonical `CHEBI:<id>` (plus ChEMBL xref where present)
- Evidence doc: canonical `PMID:<id>`

### Core mapping tables to build first

- `idmap_gene`:
  - `entrez_id`, `ensembl_gene_id`, `hgnc_symbol`, `uniprot_id`, `string_protein_id`
- `idmap_disease`:
  - `mesh_id`, `mim_id`, `doid`, `name_norm`
- `idmap_chemical`:
  - `chebi_id`, `chembl_id`, `drug_name_norm`

These should be treated as first-class assets, not ad-hoc joins.

## Recommended GCP Setup

### Storage layers

1. Raw (`bronze`): keep original files in GCS, immutable.
2. Normalized (`silver`): BigQuery cleaned/typed tables per source.
3. Graph serving (`gold`): BigQuery edge/node/evidence tables optimized for neighbor lookup.

### BigQuery datasets (example)

- `kg_raw` (external/load tables from GCS)
- `kg_norm` (source-specific cleaned tables)
- `kg_graph` (unified graph tables consumed by API)

### Graph-serving schema (gold)

- `kg_graph.nodes`
  - `node_id` (canonical CURIE)
  - `node_type`
  - `display_name`
  - `xrefs` (ARRAY<STRUCT<namespace,id>>)
- `kg_graph.edges`
  - `edge_id`
  - `src_node_id`
  - `dst_node_id`
  - `predicate`
  - `source_dataset`
  - `confidence_score`
  - `evidence_count`
  - `pmids` (ARRAY<INT64>)
  - `provenance_type` (`curated`, `text_mined`, `mixed`)
- `kg_graph.evidence`
  - `edge_id`
  - `pmid`
  - `snippet` (optional)
  - `pub_year`
  - `source_dataset`

## Query Efficiency for Interactive Graph UI

### Required query pattern

- frequent, low-latency point lookups by `src_node_id`
- top-k neighbors with filters (`predicate`, `score`, `provenance`)
- evidence lookup by `edge_id`

### BigQuery optimization choices

- Cluster `kg_graph.edges` by:
  - `src_node_id`, `predicate`, `source_dataset`
- Optionally partition edges by `source_dataset` (or ingest date) if table becomes very large.
- Cluster `kg_graph.evidence` by:
  - `edge_id`, `pmid`
- Precompute denormalized neighbor ranks:
  - `neighbor_rank` per `(src_node_id, predicate)` by score/evidence.
- Materialize seed-specific demo views:
  - BRCA1 and Imatinib subgraphs for deterministic demo speed.

### API serving approach

- Cloud Run FastAPI calls BigQuery with parameterized SQL.
- Add Redis/memory cache for hot neighborhoods:
  - key: `(node_id, filters, hop)`
  - TTL: short during development, longer for demo.
- Keep hop expansion server-side (avoid client-side multi-query fan-out).

## Suggested MVP Ingestion Order

1. Reactome gene-pathway + pathway hierarchy
2. BRCA1 association CSV + DisGeNET/Open Targets edges
3. ChEMBL drug-target tables (BigQuery public dataset)
4. STRING interactions (with Entrez bridge)
5. PKG2 paper/entity links for evidence grounding

This sequence gives a working biological path quickly, then adds depth/evidence.

## Recommended Architectural Decision (for Hackathon)

Prefer **BigQuery-backed graph tables + cached API** over standing up Neo4j now.

Why for this repo/timeline:

- Data already resides in GCS/BigQuery ecosystem.
- Team already has GCP project friction; minimizing new infra reduces risk.
- You can still emit graph-native JSON for Cytoscape without a graph DB.
- If needed later, export `kg_graph.edges/nodes` into Neo4j as a post-hackathon step.

## Immediate Next Technical Tasks

1. Build `idmap_gene` from Reactome + STRING aliases + ENSG bridge.
2. Create first `kg_graph.edges` from Reactome + BRCA1 associations.
3. Add evidence attachment from PKG2 (`PMID` links).
4. Implement `/neighbors/{node_id}` and `/edge/{edge_id}/evidence` over `kg_graph`.
