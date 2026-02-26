**Date:** Feb 25, 2026 (night before)
**Hackathon:** Feb 26 (8:30am–8pm) → Feb 27 (8:30am–1:30pm submission deadline)
**Location:** BenchSci, 559 College St Suite 201, Toronto
**Challenge:** #5 — From Wandering to Wisdom

---

## What We're Building
A **three-pane web app** for interactive multi-hop biomedical knowledge graph exploration.

**Left pane:** Search + entity card (autocomplete across genes, drugs, diseases, pathways)
**Centre pane:** Interactive graph canvas (Cytoscape.js) — 1-hop neighbors, click-to-expand, progressive disclosure
**Right pane:** Evidence + AI rationale panel — papers, snippets, provenance badges, Gemini-generated rationale on edge click

### Demo Scenarios
1. **BRCA1 (primary):** BRCA1 → DNA repair / homologous recombination → breast cancer → PARP inhibitors (olaparib)
2. **Imatinib (stress test):** Imatinib → BCR-ABL tyrosine kinase → chronic myeloid leukaemia

### Key Design Principle
> Curated edges (Reactome, DisGeNET) provide the **biological logic**. PKG + PubMed provide the **evidence and provenance**. Neither alone is sufficient.

---

## Challenge 5 Requirements

### Minimum Bar (must hit)
- Entity search (genes, diseases, drugs, pathways)
- 1-hop interactive graph visualization
- Click-to-expand ≥2 hops deep
- Evidence per connection (paper/citation/snippet)
- Path tracking (user can retrace their reasoning chain)
- Complete BRCA1 scenario end-to-end

### Competitive (pick ≥2)
- Multiple entity types in one view (gene → pathway → drug → disease)
- Filter/rank connections by evidence strength or recency
- Second scenario (Imatinib)
- Summary view of full path with aggregated evidence

### Stretch
- Side-by-side path comparison
- Surface non-obvious connections
- Export reasoning chain as shareable artifact with citations

---

## Judging Criteria
| Criteria | Weight |
|---|---|
| Solution impact & relevance | 30 pts |
| Technical execution & novelty | 30 pts |
| **Use of Google Cloud** | 20 pts |
| Presentation & demo | 20 pts |

**Key judge questions:** Does it work end-to-end with real data? Would a biologist trust the results? Did they use GCP services appropriately? Can a non-specialist follow the narrative?

---

## Tech Stack

### Must use GCP (no third-party commercial services!)
- ⚠️ **Claude API is NOT allowed** — use **Gemini via Vertex AI** for LLM rationale generation
- Backend: **FastAPI (Python)** on Cloud Run
- Frontend: **Vite React + three.js**
- Data warehouse: **BigQuery** (preferred by organizers)
- DB: ?? we are unsure - we need to look at datasets and normalise them
- LLM: **Gemini via Vertex AI** — called on edge click only, grounded in retrieved snippets
- Evidence retrieval: **PubMed E-utilities API** (free, no auth for abstracts)
- Protein metadata: **UniProt REST API** (free, no auth, call at runtime)

### GCP Resources Available
- One dedicated GCP project with preset budget
- One L4 GPU (probably won't need it)
- BigQuery, Vertex AI, Cloud Run, Cloud SQL, Firebase, GKE, Dataflow all available
- ChEMBL already pre-loaded in BigQuery: `patents-public-data.ebi_chembl.*`

---

## Data Sources — Status as of Tonight

| Source | What it gives us | Edge types | Status |
|---|---|---|---|
| **Reactome (6 files)** | Pathway data, gene-pathway mappings, protein interactions, reaction PMIDs | gene→pathway, pathway→pathway, protein↔protein, gene↔gene (FIs with annotations!) | ✅ Downloaded to desktop. Copy to GCP bucket tomorrow AM |
| **DisGeNET** | Gene-disease associations with scores, sources, PMIDs | gene→disease | ✅ 7-day trial activated. API access available. Query programmatically for BRCA1/Imatinib neighborhoods |
| **Open Targets** | Gene-disease associations with evidence scores by data source type | gene→disease (backup/supplement to DisGeNET) | ✅ Available directly on GCS: `gs://open-targets-data-releases/25.12/output/association_overall_direct`. One command to copy |
| **ChEMBL** | Drug-target interactions, mechanism of action, clinical phase | drug→target, drug metadata | ✅ Already in BigQuery: `patents-public-data.ebi_chembl.*` |
| **PubMed E-utilities** | Abstracts, citations, evidence snippets | Evidence layer (no download) | ✅ Free API, call at runtime |
| **UniProt REST API** | Protein names, functions, metadata | Node metadata (no download) | ✅ Free API, call at runtime |

### Reactome Files Downloaded (6 total)
1. `NCBI2Reactome_All_Levels.txt` — NCBI Gene ID → all pathways (gene→pathway edges)
2. `ReactomePathways.txt` — pathway names and IDs
3. `ReactomePathwaysRelation.txt` — parent-child pathway hierarchy (pathway→pathway edges)
4. `ReactionPMIDS.txt` — reaction → PubMed IDs (provenance layer)
5. `reactome.homo_sapiens.interactions.tab-delimited.txt` — human protein-protein interactions
6. `FIsInGene_04142025_with_annotations.txt.zip` — gene-gene functional interactions WITH typed annotations (activates, inhibits, complexes with). **This is the richest edge file.**

### ⚠️ DisGeNET Note
Bulk downloads are paywalled (premium only). We have **API access** via 7-day trial. Tomorrow: query the API for BRCA1 and Imatinib-relevant neighborhoods and cache results. Save your API key somewhere the team can access.

**DisGeNET API example:** `https://www.disgenet.com/api/gda/gene/672` (672 = BRCA1 NCBI Gene ID)
**API docs/examples:** https://disgenet.com/Profile-area#examples

### Open Targets GCS Copy Command
```bash
gcloud storage cp -r --billing-project ${PROJECT_ID} gs://open-targets-data-releases/25.12/output/association_overall_direct/ .
```

---

## Graph Schema (Biolink-aligned)

### Node Types
- Gene (NCBI Gene ID)
- Disease (UMLS / Disease Ontology)
- Drug / Chemical (ChEMBL ID)
- Pathway (Reactome Stable ID)
- Protein (UniProt ID)

### Edge Model (every edge is an auditable claim)
- **Type:** Biolink-aligned predicate (e.g., `gene_associated_with_condition`, `participates_in`, `treats`, `interacts_with`)
- **Direction**
- **Confidence/score**
- **Evidence objects:** PMID/DOI, extracted snippet, publication year
- **Provenance flag:** curated DB vs text-mined vs manual

### Key Design Rule
> The LLM may only cite evidence shown to the user. Any generated rationale that cannot be traced to a displayed snippet is a bug, not a feature.

---

## Submission Requirements
- **Deadline:** Feb 27 at 1:30pm EST
- **Demo video:** 3 minutes max, unlisted YouTube upload
- **Working prototype** (provide link)
- **Short project description** (problem statement, solution, tools used)
- **Code repository link**
- **Short readme + license attributions**

---

## Morning Priorities (First 2 Hours)

### Hour 0–1: Data Setup (Khash + Aditya)
1. Copy Reactome files from desktop → GCP bucket
2. Run Open Targets GCS copy command
3. Query DisGeNET API for BRCA1 neighborhood (gene ID 672) and cache
4. Query DisGeNET API for BCR-ABL / Imatinib neighborhood and cache
5. Explore ChEMBL in BigQuery — find drug→target table for olaparib and imatinib

### Hour 0–1: Frontend Scaffold (Ganni)
1. React app skeleton with three-pane layout
2. Cytoscape.js installed and rendering a hardcoded test graph
3. Deploy to Cloud Run (even if empty — proves infra works)

### Hour 0–1: Design (Jules)
1. Wireframe the three-pane layout
2. Define information hierarchy: what shows on node hover, edge click, entity card
3. Design provenance badges (curated vs text-mined distinction)

### Hour 1–2: Graph DB + API (Aditya + Khash)
1. Load Reactome + DisGeNET data into graph structure (Neo4j on GKE or in-memory Python graph)
2. FastAPI skeleton with `/search`, `/neighbors/{node_id}`, `/edge/{edge_id}/evidence` endpoints
3. Wire frontend to backend — show BRCA1 with real 1-hop neighbors

---

## Open Questions for Tomorrow
- [ ] What can Alice do? Assign her accordingly
- [ ] DisGeNET API key — save somewhere team-accessible
- [ ] Neo4j vs in-memory graph? Decision depends on data volume and setup time
- [ ] How to handle entity ID normalization across sources (NCBI Gene ID ↔ UniProt ↔ ChEMBL)

---

## Key Links
- Hackathon Playbook: https://docs.google.com/document/d/1ozYTApMXW1iXNoYVthA1EnwZFsZMk_Vn8446AB3dxVs/edit
- Submission form: https://docs.google.com/forms/d/e/1FAIpQLSfSvbyNIJeUB6cj5faBoZZH9cGUFnfJDvxyxQ_5DMxs1bjPpQ/viewform
- Reactome downloads: https://reactome.org/download-data
- DisGeNET API: https://disgenet.com/Profile-area#examples
- Open Targets downloads: https://platform.opentargets.org/downloads
- Biolink Model predicates: https://biolink.github.io/biolink-model/#predicates-visualization
- PubMed E-utilities: https://www.ncbi.nlm.nih.gov/home/develop/api/
- UniProt REST API: https://rest.uniprot.org/
- Jules portfolio: https://julespark.design/
