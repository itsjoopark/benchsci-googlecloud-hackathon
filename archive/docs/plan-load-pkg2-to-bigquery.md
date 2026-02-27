# Plan: Load PKG 2.0 Data from GCS into BigQuery

## Context

The PKG 2.0 PubMed dataset (12 TSV.gz files, ~3.2 GB compressed) has been downloaded to `gs://multihopwanderer-1771992134-team-bucket/pkg2/`. These need to be loaded into BigQuery as raw tables in a `kg_raw` dataset, which will serve as the foundation for the downstream `kg_norm` and `kg_graph` layers defined in `docs/day-0-planning.md`.

## Approach

Create a shell script `scripts/gcp/load_pkg2_to_bigquery.sh` that uses `bq load` to load all 12 files into BigQuery tables.

### Key decisions
- **`bq load` CLI** (not Python) — matches existing script conventions in the repo
- **Explicit schemas for C-prefix tables** (paper provides exact types) + **autodetect for A-prefix tables** (schemas not in the paper, but TSV headers are present)
- **`--replace`** (WRITE_TRUNCATE) for idempotency — re-running overwrites cleanly
- **DATE fallback** — if DATE columns fail to parse, auto-retry with STRING type

## Tables and Schemas

### C-prefix tables (explicit schemas from PKG 2.0 paper)

| Table | Schema | File Size |
|-------|--------|-----------|
| `C23_BioEntities` | EntityId:STRING, Type:STRING, Mention:STRING | 4.4 MB |
| `C01_Papers` | PMID:INT64, PubYear:INT64, ArticleTitle:STRING, AuthorNum:INT64, CitedCount:INT64, IsClinical:INT64 | 741.8 MB |
| `C06_Link_Papers_BioEntities` | PMID:INT64, StartPosition:INT64, EndPosition:INT64, Mention:STRING, Entityid:STRING, Type:INT64, is_neural_normalized:INT64 | 216.8 MB |
| `C11_ClinicalTrials` | nct_id:STRING, brief_title:STRING, start_date:DATE | 217.4 MB |
| `C13_Link_ClinicalTrials_BioEntities` | nct_id:STRING, Entityid:STRING | 169.7 MB |
| `C15_Patents` | PatentId:STRING, GrantedDate:DATE, Title:STRING, Abstract:STRING | 108.8 MB |
| `C18_Link_Patents_BioEntities` | PatentId:STRING, StartPosition:INT64, EndPosition:INT64, Mention:STRING, Entityid:STRING, Type:INT64 | 110.9 MB |
| `C21_Bioentity_Relationships` | PMID:INT64, entity_id1:STRING, entity_id2:STRING, relation_type:STRING, relation_id:STRING | 217.1 MB |

### A-prefix tables (autodetect from TSV headers)

| Table | File Size |
|-------|-----------|
| `A01_Articles` | 426.7 MB |
| `A03_KeywordList` | 637.8 MB |
| `A04_Abstract` | 111 MB |
| `A06_MeshHeadingList` | 116 MB |

## Script structure (`scripts/gcp/load_pkg2_to_bigquery.sh`)

```
1. Config: PROJECT_ID, DATASET=kg_raw, GCS_PREFIX, BQ_COMMON_FLAGS
2. Validate: check bq/gsutil available, verify GCS access
3. Create dataset: bq mk --dataset kg_raw --location=us-central1 (idempotent)
4. Load C23_BioEntities first (4.4 MB — fast sanity check)
5. Load remaining C-prefix tables with explicit schemas
   - DATE fallback for C11 and C15 if parse fails
6. Load A-prefix tables with --autodetect
7. Print summary: pass/fail per table + row counts
```

Common `bq load` flags:
- `--source_format=CSV --field_delimiter=tab --skip_leading_rows=1`
- `--replace --max_bad_records=0`
- `--project_id=multihopwanderer-1771992134`

## Files to create/modify

| File | Action |
|------|--------|
| `scripts/gcp/load_pkg2_to_bigquery.sh` | **Create** — main load script |

## Verification

1. Run `source scripts/gcp/switch-config.sh && use_multihop` to set auth
2. Run `bash scripts/gcp/load_pkg2_to_bigquery.sh`
3. Verify all 12 tables show "PASS" in summary
4. Verify row counts are non-zero for all tables
5. Quick spot-check: `bq query 'SELECT * FROM kg_raw.C23_BioEntities LIMIT 5'`
