# PKG2 Vectorization Deployment (GCS -> Vertex Vector Search)

This repo is now organized around the **active deployment path** for PKG2 vectorization:
- source docs in BigQuery (`kg_raw`)
- streaming + sharded embedding
- JSONL datapoints in GCS
- batch index build in Vertex AI Vector Search

## Active components

- Pipeline modules:
  - `src/pilot_rag/config.py`
  - `src/pilot_rag/bq_store.py`
  - `src/pilot_rag/chunking.py`
  - `src/pilot_rag/vertex_client.py`
  - `src/pilot_rag/gcs_index_pipeline.py`
- Build CLI:
  - `scripts/pilot/build_gcs_batch_index.py`
- Python deps:
  - `requirements-pilot.txt`

## Scope and behavior

- Project: `multihopwanderer-1771992134`
- Embedding model: `gemini-embedding-001` (fallback `text-embedding-005`)
- Full-mode corpus gate: non-empty text docs with `COUNT(DISTINCT normalized_entity_id) >= MIN_LINKED_ENTITIES`
- Default for current run: no entity-type filter
- Conservative quota-aware embedding profile supported (workers + backoff + retry)

## Source tables

Default `SOURCE_BQ_DATASET=kg_raw`:
- `A04_Abstract`
- `C11_ClinicalTrials`
- `C15_Patents`
- `C06_Link_Papers_BioEntities`
- `C13_Link_ClinicalTrials_BioEntities`
- `C18_Link_Patents_BioEntities`

## CLI usage

Install deps:

```bash
pip3 install -r requirements-pilot.txt
```

Metadata-only dry run:

```bash
python3 scripts/pilot/build_gcs_batch_index.py \
  --mode full \
  --bucket multihopwanderer-1771992134-team-bucket \
  --limit 0 \
  --min-linked-entities 2 \
  --no-type-filter \
  --dry-run
```

Full run (streaming/sharded):

```bash
python3 scripts/pilot/build_gcs_batch_index.py \
  --mode full \
  --bucket multihopwanderer-1771992134-team-bucket \
  --limit 0 \
  --batch-docs 10000 \
  --workers 2 \
  --max-retries 6 \
  --min-linked-entities 2 \
  --no-type-filter
```

Resume run:

```bash
python3 scripts/pilot/build_gcs_batch_index.py \
  --mode full \
  --bucket multihopwanderer-1771992134-team-bucket \
  --resume-run-id <run_id> \
  --limit 0 \
  --batch-docs 10000 \
  --workers 2 \
  --max-retries 6 \
  --min-linked-entities 2 \
  --no-type-filter
```

## Output artifacts

For run prefix `gs://<bucket>/<prefix>`:
- `manifest_stats.json`
- `checkpoint.json`
- `run_summary.json`
- `failed_chunks.jsonl` (if any failures)
- `shards/part-xxxxx.jsonl`

## Key env vars

- `GCP_PROJECT_ID` (default `multihopwanderer-1771992134`)
- `GCP_LOCATION` (default `us-central1`)
- `SOURCE_BQ_DATASET` (default `kg_raw`)
- `VERTEX_EMBEDDING_MODEL` (default `gemini-embedding-001`)
- `VERTEX_EMBEDDING_MODEL_FALLBACK` (default `text-embedding-005`)
- `EMBED_WORKERS` (default `2`)
- `EMBED_BATCH_SIZE` (default `250`)
- `EMBED_MAX_RETRIES` (default `6`)
- `EMBED_BASE_BACKOFF_MS` (default `500`)
- `EMBED_REQUEST_INTERVAL_MS` (default `100`)
- `MIN_LINKED_ENTITIES` (default `2`)
- `ENABLE_ENTITY_TYPE_FILTER` (default `false`)

## Latest validation

- Full-mode dry run succeeded (manifest/write only).
- Full-mode streaming smoke test succeeded (`--limit 100 --skip-index`):
  - docs: `100`
  - chunks: `113`
  - embedded: `113`
  - failures: `0`
