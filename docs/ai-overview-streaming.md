# AI Overview Streaming (Gemini 3 Flash + RAG)

This feature adds a streaming AI explanation sidebar for node/edge clicks.

## Backend env vars

Set these in `backend/.env` (or environment):

```bash
GEMINI_OVERVIEW_MODEL=gemini-3-flash-preview
VERTEX_VECTOR_ENDPOINT_RESOURCE=projects/<project>/locations/<region>/indexEndpoints/<id>
VERTEX_VECTOR_DEPLOYED_INDEX_ID=<deployed-index-id>
OVERVIEW_HISTORY_LIMIT=3
OVERVIEW_RAG_TOP_K=20
OVERVIEW_RAG_FETCH_K=150
OVERVIEW_RAG_DATASET=multihopwanderer
OVERVIEW_RAG_EMBED_TABLE=evidence_embeddings_pilot
OVERVIEW_RAG_ENTITY_TABLE=evidence_doc_entities_pilot
```

## Verify vector readiness

### In-process verifier

```bash
python3 scripts/gcp/verify_overview_vector.py
```

### HTTP verifier route

```bash
curl -s http://localhost:8000/api/overview/verify | jq
```

## Stream endpoint

`POST /api/overview/stream` (SSE)

SSE events:
- `start`
- `context`
- `delta`
- `done`
- `error`

## CLI smoke test for stream

1. Save a request payload:

```json
{
  "selection_type": "edge",
  "edge_id": "NCBIGene:672--MESH:D001943--disease_associated_with_gene",
  "center_node_id": "NCBIGene:672",
  "entities": [
    {"id": "NCBIGene:672", "name": "BRCA1", "type": "gene"},
    {"id": "MESH:D001943", "name": "Breast Neoplasms", "type": "disease"}
  ],
  "edges": [
    {
      "id": "NCBIGene:672--MESH:D001943--disease_associated_with_gene",
      "source": "NCBIGene:672",
      "target": "MESH:D001943",
      "predicate": "biolink:related_to",
      "label": "related to",
      "score": 0.87,
      "provenance": "literature",
      "sourceDb": "kg_raw",
      "evidence": [
        {
          "id": "ev-0",
          "pmid": "12345678",
          "title": "BRCA1 and breast cancer risk",
          "year": 2018,
          "snippet": "BRCA1 variants are associated with hereditary breast cancer.",
          "source": "PubMed",
          "sourceDb": "PubMed"
        }
      ]
    }
  ],
  "history": []
}
```

2. Stream events:

```bash
./scripts/gcp/stream_overview_cli.sh /path/to/request.json http://localhost:8000
```

## Direct Vertex model smoke test

```bash
./scripts/gcp/vertex_overview_direct.sh "Explain BRCA1 to breast cancer connection with citations."
```

This validates model streaming separately from app/server logic.
