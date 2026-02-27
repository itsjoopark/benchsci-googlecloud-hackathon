#!/usr/bin/env python3
"""Materialize overview RAG BigQuery tables from Vertex shard artifacts in GCS.

Repeatable workflow:
1) Load shard JSONL (`id`, `embedding`, `embedding_metadata`) into a typed staging table.
2) Build/replace embeddings table with chunk metadata + embedding.
3) Reconstruct `chunk_text` deterministically from source docs using chunking settings.
4) Build/replace doc-entity table for the same docs.

Example:
  PYTHONPATH=. python scripts/gcp/materialize_overview_rag_tables.py \
    --gcs-prefix gs://multihopwanderer-1771992134-team-bucket/vector-search/pkg2-full/20260226T232643Z \
    --project-id multihopwanderer-1771992134 \
    --target-dataset kg_raw \
    --source-dataset kg_raw \
    --location us-central1
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from google.cloud import bigquery

from src.pilot_rag.chunking import chunk_document
from src.pilot_rag.config import SETTINGS


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gcs-prefix", required=True, help="GCS run prefix, e.g. gs://bucket/vector-search/pkg2-full/<run_id>")
    p.add_argument("--project-id", default=SETTINGS.project_id)
    p.add_argument("--source-dataset", default=SETTINGS.source_bq_dataset)
    p.add_argument("--target-dataset", default="kg_raw")
    p.add_argument("--embed-table", default="evidence_embeddings_pilot")
    p.add_argument("--entity-table", default="evidence_doc_entities_pilot")
    p.add_argument("--location", default="us-central1")
    p.add_argument("--doc-batch-size", type=int, default=2000)
    p.add_argument("--chunk-text-flush", type=int, default=25000)
    p.add_argument("--max-chunk-chars", type=int, default=SETTINGS.max_chunk_chars)
    p.add_argument("--chunk-overlap-chars", type=int, default=SETTINGS.chunk_overlap_chars)
    p.add_argument("--resume", action="store_true", help="Resume from existing embeddings table; only backfill missing chunk_text.")
    p.add_argument("--skip-entity-refresh", action="store_true", help="Skip rebuilding entity table.")
    p.add_argument("--keep-temp", action="store_true")
    return p.parse_args()


def _run_query(client: bigquery.Client, sql: str, location: str) -> None:
    client.query(sql, location=location).result()


def _query_rows(client: bigquery.Client, sql: str, params: list[bigquery.QueryParameter], location: str):
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return client.query(sql, job_config=cfg, location=location).result()


def _table_exists(client: bigquery.Client, table_ref: str) -> bool:
    try:
        client.get_table(table_ref)
        return True
    except Exception:
        return False


def main() -> None:
    args = _parse_args()
    client = bigquery.Client(project=args.project_id)

    ts = int(time.time())
    stage_table = f"_tmp_rag_stage_{ts}"
    # Stable staging table name enables interrupted runs to continue cleanly.
    chunk_text_stage = f"_tmp_rag_chunk_text_stage_{args.embed_table}"

    target_embed_fq = f"`{args.project_id}.{args.target_dataset}.{args.embed_table}`"
    target_entity_fq = f"`{args.project_id}.{args.target_dataset}.{args.entity_table}`"
    stage_fq = f"`{args.project_id}.{args.target_dataset}.{stage_table}`"
    chunk_stage_fq = f"`{args.project_id}.{args.target_dataset}.{chunk_text_stage}`"

    shards_glob = f"{args.gcs_prefix.rstrip('/')}/shards/*"

    embed_table_ref = f"{args.project_id}.{args.target_dataset}.{args.embed_table}"
    if args.resume and _table_exists(client, embed_table_ref):
        print(f"[1/6] Resume mode: using existing embeddings table: {target_embed_fq}")
    else:
        print(f"[1/6] Loading shard JSONL into staging table: {shards_glob}")
        stage_ref = f"{args.project_id}.{args.target_dataset}.{stage_table}"
        stage_schema = [
            bigquery.SchemaField("id", "STRING"),
            bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
            bigquery.SchemaField(
                "embedding_metadata",
                "RECORD",
                fields=[
                    bigquery.SchemaField("doc_id", "STRING"),
                    bigquery.SchemaField("doc_type", "STRING"),
                    bigquery.SchemaField("source_id", "STRING"),
                    bigquery.SchemaField("chunk_index", "INT64"),
                    bigquery.SchemaField("entity_count", "INT64"),
                    bigquery.SchemaField("run_id", "STRING"),
                    bigquery.SchemaField("model_id", "STRING"),
                ],
            ),
        ]
        load_cfg = bigquery.LoadJobConfig(
            schema=stage_schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            ignore_unknown_values=True,
            max_bad_records=0,
        )
        client.load_table_from_uri(shards_glob, stage_ref, job_config=load_cfg, location=args.location).result()

        print(f"[2/6] Creating/replacing embeddings table: {target_embed_fq}")
        _run_query(
            client,
            f"""
            CREATE OR REPLACE TABLE {target_embed_fq} AS
            SELECT
              CAST(id AS STRING) AS chunk_id,
              CAST(embedding_metadata.doc_id AS STRING) AS doc_id,
              CAST(embedding_metadata.doc_type AS STRING) AS doc_type,
              CAST(embedding_metadata.source_id AS STRING) AS source_id,
              SAFE_CAST(embedding_metadata.chunk_index AS INT64) AS chunk_index,
              CAST(NULL AS STRING) AS chunk_text,
              embedding AS embedding,
              CAST(embedding_metadata.run_id AS STRING) AS run_id,
              CAST(embedding_metadata.model_id AS STRING) AS model_id
            FROM {stage_fq}
            WHERE id IS NOT NULL
              AND embedding_metadata.doc_id IS NOT NULL
            """,
            args.location,
        )

    print(f"[3/6] Reconstructing chunk_text into staging table: {chunk_stage_fq}")
    schema = [
        bigquery.SchemaField("chunk_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("chunk_text", "STRING", mode="REQUIRED"),
    ]
    client.create_table(
        bigquery.Table(f"{args.project_id}.{args.target_dataset}.{chunk_text_stage}", schema=schema),
        exists_ok=True,
    )

    doc_sql = f"""
    SELECT DISTINCT doc_id, doc_type
    FROM {target_embed_fq}
    WHERE chunk_text IS NULL OR TRIM(chunk_text) = ''
    """
    docs = list(client.query(doc_sql, location=args.location).result())
    total_docs = len(docs)
    print(f"  docs to reconstruct: {total_docs}")

    docs_union_sql = f"""
    WITH paper_docs AS (
      SELECT
        CONCAT('PMID:', CAST(COALESCE(a.PMID, c.PMID) AS STRING)) AS doc_id,
        'paper' AS doc_type,
        CAST(COALESCE(a.PMID, c.PMID) AS STRING) AS source_id,
        CASE
          WHEN a.AbstractText IS NOT NULL AND TRIM(a.AbstractText) != '' THEN a.AbstractText
          WHEN c.ArticleTitle IS NOT NULL AND TRIM(c.ArticleTitle) != '' THEN c.ArticleTitle
          ELSE NULL
        END AS text
      FROM `{args.project_id}.{args.source_dataset}.{SETTINGS.source_table_a04}` a
      FULL OUTER JOIN `{args.project_id}.{args.source_dataset}.C01_Papers` c
        ON a.PMID = c.PMID
      WHERE COALESCE(a.PMID, c.PMID) IS NOT NULL
    ),
    trial_docs AS (
      SELECT
        CONCAT('NCT:', nct_id) AS doc_id,
        'trial' AS doc_type,
        nct_id AS source_id,
        TRIM(CONCAT(
          IFNULL(brief_summaries, ''), ' ',
          IFNULL(detailed_descriptions, ''), ' ',
          IFNULL(brief_title, ''), ' ',
          IFNULL(official_title, ''), ' ',
          IFNULL(conditions, ''), ' ',
          IFNULL(keywords, '')
        )) AS text
      FROM `{args.project_id}.{args.source_dataset}.{SETTINGS.source_table_c11}`
      WHERE TRIM(CONCAT(
        IFNULL(brief_summaries, ''), ' ',
        IFNULL(detailed_descriptions, ''), ' ',
        IFNULL(brief_title, ''), ' ',
        IFNULL(official_title, ''), ' ',
        IFNULL(conditions, ''), ' ',
        IFNULL(keywords, '')
      )) != ''
    ),
    patent_docs AS (
      SELECT
        CONCAT('PATENT:', PatentId) AS doc_id,
        'patent' AS doc_type,
        PatentId AS source_id,
        Abstract AS text
      FROM `{args.project_id}.{args.source_dataset}.{SETTINGS.source_table_c15}`
      WHERE Abstract IS NOT NULL AND TRIM(Abstract) != ''
    ),
    all_docs AS (
      SELECT * FROM paper_docs
      UNION ALL SELECT * FROM trial_docs
      UNION ALL SELECT * FROM patent_docs
    )
    SELECT doc_id, doc_type, text
    FROM all_docs
    WHERE text IS NOT NULL AND TRIM(text) != ''
      AND doc_id IN UNNEST(@doc_ids)
    """

    expected_sql = f"""
    SELECT doc_id, chunk_id
    FROM {target_embed_fq}
    WHERE doc_id IN UNNEST(@doc_ids)
    """

    pending_rows: list[dict] = []

    def flush_chunk_rows(rows: list[dict]) -> None:
        if not rows:
            return
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tf:
            tmp_path = Path(tf.name)
            for r in rows:
                tf.write(json.dumps(r, ensure_ascii=False) + "\n")

        table_ref = f"{args.project_id}.{args.target_dataset}.{chunk_text_stage}"
        cfg = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        with tmp_path.open("rb") as f:
            client.load_table_from_file(f, table_ref, job_config=cfg, location=args.location).result()
        tmp_path.unlink(missing_ok=True)
        _run_query(
            client,
            f"""
            MERGE {target_embed_fq} t
            USING (
              SELECT chunk_id, ANY_VALUE(chunk_text) AS chunk_text
              FROM {chunk_stage_fq}
              GROUP BY chunk_id
            ) s
            ON t.chunk_id = s.chunk_id
            WHEN MATCHED THEN
              UPDATE SET t.chunk_text = s.chunk_text
            """,
            args.location,
        )
        _run_query(client, f"TRUNCATE TABLE {chunk_stage_fq}", args.location)

    for i in range(0, total_docs, args.doc_batch_size):
        batch_docs = docs[i : i + args.doc_batch_size]
        doc_ids = [str(r["doc_id"]) for r in batch_docs]

        expected_rows = _query_rows(
            client,
            expected_sql,
            [bigquery.ArrayQueryParameter("doc_ids", "STRING", doc_ids)],
            args.location,
        )
        expected_by_doc: dict[str, set[str]] = defaultdict(set)
        for r in expected_rows:
            expected_by_doc[str(r["doc_id"])].add(str(r["chunk_id"]))

        text_rows = _query_rows(
            client,
            docs_union_sql,
            [bigquery.ArrayQueryParameter("doc_ids", "STRING", doc_ids)],
            args.location,
        )

        for r in text_rows:
            doc_id = str(r["doc_id"])
            doc_type = str(r["doc_type"])
            text = str(r["text"] or "")
            expected = expected_by_doc.get(doc_id)
            if not expected:
                continue

            for c in chunk_document(
                doc_id=doc_id,
                doc_type=doc_type,
                text=text,
                max_chars=args.max_chunk_chars,
                overlap_chars=args.chunk_overlap_chars,
            ):
                if c.chunk_id in expected:
                    pending_rows.append({"chunk_id": c.chunk_id, "chunk_text": c.text})

        if len(pending_rows) >= args.chunk_text_flush:
            flush_chunk_rows(pending_rows)
            pending_rows = []

        print(f"  processed docs: {min(i + args.doc_batch_size, total_docs)}/{total_docs}")

    flush_chunk_rows(pending_rows)

    if args.skip_entity_refresh:
        print("[5/6] Skipping entity table refresh (--skip-entity-refresh)")
    else:
        print(f"[5/6] Creating/replacing entity table: {target_entity_fq}")
        _run_query(
            client,
            f"""
        CREATE OR REPLACE TABLE {target_entity_fq} AS
        WITH target_doc_ids AS (
          SELECT DISTINCT doc_id FROM {target_embed_fq}
        ),
        paper AS (
          SELECT CONCAT('PMID:', CAST(PMID AS STRING)) AS doc_id,
                 CASE
                   WHEN NULLIF(NCBIGene, '') IS NOT NULL THEN CONCAT('NCBIGene:', NCBIGene)
                   WHEN NULLIF(CHEBI, '') IS NOT NULL THEN CONCAT('CHEBI:', CHEBI)
                   WHEN NULLIF(mesh, '') IS NOT NULL THEN CONCAT('MESH:', REGEXP_REPLACE(mesh, r'^mesh', ''))
                   WHEN NULLIF(EntityId, '') IS NOT NULL THEN EntityId
                   ELSE NULL
                 END AS entity_id,
                 LOWER(COALESCE(Type, '')) AS entity_type,
                 Mention AS mention,
                 'C06_Link_Papers_BioEntities' AS source_table
          FROM `{args.project_id}.{args.source_dataset}.{SETTINGS.source_table_c06}`
        ),
        trial AS (
          SELECT CONCAT('NCT:', nct_id) AS doc_id,
                 CASE
                   WHEN NULLIF(NCBIGene, '') IS NOT NULL THEN CONCAT('NCBIGene:', NCBIGene)
                   WHEN NULLIF(CHEBI, '') IS NOT NULL THEN CONCAT('CHEBI:', CHEBI)
                   WHEN NULLIF(mesh, '') IS NOT NULL THEN CONCAT('MESH:', REGEXP_REPLACE(mesh, r'^mesh', ''))
                   WHEN NULLIF(EntityId, '') IS NOT NULL THEN EntityId
                   ELSE NULL
                 END AS entity_id,
                 LOWER(COALESCE(Type, '')) AS entity_type,
                 Mention AS mention,
                 'C13_Link_ClinicalTrials_BioEntities' AS source_table
          FROM `{args.project_id}.{args.source_dataset}.{SETTINGS.source_table_c13}`
        ),
        patent AS (
          SELECT CONCAT('PATENT:', PatentId) AS doc_id,
                 CASE
                   WHEN NULLIF(NCBIGene, '') IS NOT NULL THEN CONCAT('NCBIGene:', NCBIGene)
                   WHEN NULLIF(CHEBI, '') IS NOT NULL THEN CONCAT('CHEBI:', CHEBI)
                   WHEN NULLIF(mesh, '') IS NOT NULL THEN CONCAT('MESH:', REGEXP_REPLACE(mesh, r'^mesh', ''))
                   WHEN NULLIF(EntityId, '') IS NOT NULL THEN EntityId
                   ELSE NULL
                 END AS entity_id,
                 LOWER(COALESCE(Type, '')) AS entity_type,
                 Mention AS mention,
                 'C18_Link_Patents_BioEntities' AS source_table
          FROM `{args.project_id}.{args.source_dataset}.{SETTINGS.source_table_c18}`
        ),
        all_links AS (
          SELECT * FROM paper
          UNION ALL SELECT * FROM trial
          UNION ALL SELECT * FROM patent
        )
        SELECT doc_id, entity_id, entity_type, mention, source_table
        FROM all_links
        WHERE doc_id IN (SELECT doc_id FROM target_doc_ids)
          AND entity_id IS NOT NULL
            """,
            args.location,
        )

    coverage_sql = f"""
    SELECT
      COUNT(*) AS chunks_total,
      COUNTIF(chunk_text IS NOT NULL AND TRIM(chunk_text) != '') AS chunks_with_text,
      COUNT(DISTINCT doc_id) AS docs_total
    FROM {target_embed_fq}
    """
    cov = list(client.query(coverage_sql, location=args.location).result())[0]

    if args.skip_entity_refresh:
        ent_links = -1
        ent_docs = -1
    else:
        ent_sql = f"SELECT COUNT(*) AS entity_links, COUNT(DISTINCT doc_id) AS entity_docs FROM {target_entity_fq}"
        ent = list(client.query(ent_sql, location=args.location).result())[0]
        ent_links = int(ent["entity_links"])
        ent_docs = int(ent["entity_docs"])

    print("[6/6] Done")
    print(
        json.dumps(
            {
                "project": args.project_id,
                "location": args.location,
                "gcs_prefix": args.gcs_prefix,
                "target_dataset": args.target_dataset,
                "embed_table": args.embed_table,
                "entity_table": args.entity_table,
                "chunks_total": int(cov["chunks_total"]),
                "chunks_with_text": int(cov["chunks_with_text"]),
                "docs_total": int(cov["docs_total"]),
                "entity_links": ent_links,
                "entity_docs": ent_docs,
            },
            indent=2,
        )
    )

    if not args.keep_temp:
        temps = [chunk_text_stage]
        if not (args.resume and _table_exists(client, embed_table_ref)):
            temps.append(stage_table)
        for t in temps:
            client.delete_table(f"{args.project_id}.{args.target_dataset}.{t}", not_found_ok=True)


if __name__ == "__main__":
    main()
