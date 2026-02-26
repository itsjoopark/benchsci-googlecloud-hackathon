from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from google.cloud import bigquery

from .config import SETTINGS


@dataclass
class EvidenceDoc:
    doc_id: str
    doc_type: str
    source_id: str
    text: str
    entity_count: int = 0


@dataclass
class DocEntity:
    doc_id: str
    entity_id: str
    entity_type: str
    mention: str
    source_table: str


class BQStore:
    def __init__(
        self,
        project_id: str = SETTINGS.project_id,
        source_dataset: str = SETTINGS.source_bq_dataset,
        target_dataset: str = SETTINGS.target_bq_dataset,
    ) -> None:
        self.project_id = project_id
        self.source_dataset = source_dataset
        self.target_dataset = target_dataset
        self.client = bigquery.Client(project=project_id)

    def _fq_source(self, table: str) -> str:
        return f"`{self.project_id}.{self.source_dataset}.{table}`"

    def _fq_target(self, table: str) -> str:
        return f"`{self.project_id}.{self.target_dataset}.{table}`"

    def fetch_pilot_docs(self, limit: int) -> list[EvidenceDoc]:
        query = f"""
        WITH paper_docs AS (
          SELECT CONCAT('PMID:', CAST(PMID AS STRING)) AS doc_id,
                 'paper' AS doc_type,
                 CAST(PMID AS STRING) AS source_id,
                 AbstractText AS text
          FROM {self._fq_source(SETTINGS.source_table_a04)}
          WHERE AbstractText IS NOT NULL AND TRIM(AbstractText) != ''
        ),
        trial_docs AS (
          SELECT CONCAT('NCT:', nct_id) AS doc_id,
                 'trial' AS doc_type,
                 nct_id AS source_id,
                 CONCAT(IFNULL(brief_summaries, ''), ' ', IFNULL(detailed_descriptions, '')) AS text
          FROM {self._fq_source(SETTINGS.source_table_c11)}
          WHERE (brief_summaries IS NOT NULL AND TRIM(brief_summaries) != '')
             OR (detailed_descriptions IS NOT NULL AND TRIM(detailed_descriptions) != '')
        ),
        patent_docs AS (
          SELECT CONCAT('PATENT:', PatentId) AS doc_id,
                 'patent' AS doc_type,
                 PatentId AS source_id,
                 Abstract AS text
          FROM {self._fq_source(SETTINGS.source_table_c15)}
          WHERE Abstract IS NOT NULL AND TRIM(Abstract) != ''
        ),
        all_docs AS (
          SELECT * FROM paper_docs
          UNION ALL SELECT * FROM trial_docs
          UNION ALL SELECT * FROM patent_docs
        ),
        with_bucket AS (
          SELECT *, MOD(ABS(FARM_FINGERPRINT(doc_id)), 3) AS bucket FROM all_docs
        )
        SELECT doc_id, doc_type, source_id, text
        FROM with_bucket
        QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_type ORDER BY doc_id) <= CAST(@per_type AS INT64)
        LIMIT @global_limit
        """
        per_type = max(1, limit // 3)
        params = [
            bigquery.ScalarQueryParameter("per_type", "INT64", per_type),
            bigquery.ScalarQueryParameter("global_limit", "INT64", limit),
        ]
        rows = self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return [EvidenceDoc(r.doc_id, r.doc_type, r.source_id, r.text, 0) for r in rows]

    def _link_union_sql(self) -> str:
        return f"""
        SELECT
          CONCAT('PMID:', CAST(PMID AS STRING)) AS doc_id,
          'paper' AS doc_type,
          LOWER(COALESCE(Type, '')) AS entity_type,
          CASE
            WHEN NULLIF(NCBIGene, '') IS NOT NULL THEN CONCAT('NCBIGene:', NCBIGene)
            WHEN NULLIF(CHEBI, '') IS NOT NULL THEN CONCAT('CHEBI:', CHEBI)
            WHEN NULLIF(mesh, '') IS NOT NULL THEN CONCAT('MESH:', REGEXP_REPLACE(mesh, r'^mesh', ''))
            WHEN NULLIF(EntityId, '') IS NOT NULL THEN EntityId
            ELSE NULL
          END AS entity_id
        FROM {self._fq_source(SETTINGS.source_table_c06)}
        UNION ALL
        SELECT
          CONCAT('NCT:', nct_id) AS doc_id,
          'trial' AS doc_type,
          LOWER(COALESCE(Type, '')) AS entity_type,
          CASE
            WHEN NULLIF(NCBIGene, '') IS NOT NULL THEN CONCAT('NCBIGene:', NCBIGene)
            WHEN NULLIF(CHEBI, '') IS NOT NULL THEN CONCAT('CHEBI:', CHEBI)
            WHEN NULLIF(mesh, '') IS NOT NULL THEN CONCAT('MESH:', REGEXP_REPLACE(mesh, r'^mesh', ''))
            WHEN NULLIF(EntityId, '') IS NOT NULL THEN EntityId
            ELSE NULL
          END AS entity_id
        FROM {self._fq_source(SETTINGS.source_table_c13)}
        UNION ALL
        SELECT
          CONCAT('PATENT:', PatentId) AS doc_id,
          'patent' AS doc_type,
          LOWER(COALESCE(Type, '')) AS entity_type,
          CASE
            WHEN NULLIF(NCBIGene, '') IS NOT NULL THEN CONCAT('NCBIGene:', NCBIGene)
            WHEN NULLIF(CHEBI, '') IS NOT NULL THEN CONCAT('CHEBI:', CHEBI)
            WHEN NULLIF(mesh, '') IS NOT NULL THEN CONCAT('MESH:', REGEXP_REPLACE(mesh, r'^mesh', ''))
            WHEN NULLIF(EntityId, '') IS NOT NULL THEN EntityId
            ELSE NULL
          END AS entity_id
        FROM {self._fq_source(SETTINGS.source_table_c18)}
        """

    def _docs_union_sql(self) -> str:
        return f"""
        SELECT
          CONCAT('PMID:', CAST(PMID AS STRING)) AS doc_id,
          'paper' AS doc_type,
          CAST(PMID AS STRING) AS source_id,
          AbstractText AS text
        FROM {self._fq_source(SETTINGS.source_table_a04)}
        WHERE AbstractText IS NOT NULL AND TRIM(AbstractText) != ''
        UNION ALL
        SELECT
          CONCAT('NCT:', nct_id) AS doc_id,
          'trial' AS doc_type,
          nct_id AS source_id,
          CONCAT(IFNULL(brief_summaries, ''), ' ', IFNULL(detailed_descriptions, '')) AS text
        FROM {self._fq_source(SETTINGS.source_table_c11)}
        WHERE (brief_summaries IS NOT NULL AND TRIM(brief_summaries) != '')
           OR (detailed_descriptions IS NOT NULL AND TRIM(detailed_descriptions) != '')
        UNION ALL
        SELECT
          CONCAT('PATENT:', PatentId) AS doc_id,
          'patent' AS doc_type,
          PatentId AS source_id,
          Abstract AS text
        FROM {self._fq_source(SETTINGS.source_table_c15)}
        WHERE Abstract IS NOT NULL AND TRIM(Abstract) != ''
        """

    def fetch_manifest_stats(
        self,
        min_linked_entities: int,
        enable_entity_type_filter: bool = False,
        allowed_entity_types: list[str] | None = None,
    ) -> dict:
        allowed_entity_types = [t.lower() for t in (allowed_entity_types or [])]
        query = f"""
        WITH docs AS (
          {self._docs_union_sql()}
        ),
        links AS (
          {self._link_union_sql()}
        ),
        filtered_links AS (
          SELECT * FROM links
          WHERE entity_id IS NOT NULL
            AND (@enable_type_filter = FALSE OR entity_type IN UNNEST(@allowed_types))
        ),
        doc_counts AS (
          SELECT doc_id, doc_type, COUNT(DISTINCT entity_id) AS entity_count
          FROM filtered_links
          GROUP BY doc_id, doc_type
        ),
        eligible AS (
          SELECT d.doc_id, d.doc_type
          FROM docs d
          JOIN doc_counts c USING (doc_id, doc_type)
          WHERE c.entity_count >= @min_linked_entities
        )
        SELECT
          COUNT(*) AS docs_total,
          COUNTIF(doc_type = 'paper') AS docs_paper,
          COUNTIF(doc_type = 'trial') AS docs_trial,
          COUNTIF(doc_type = 'patent') AS docs_patent
        FROM eligible
        """
        params = [
            bigquery.ScalarQueryParameter("min_linked_entities", "INT64", min_linked_entities),
            bigquery.ScalarQueryParameter("enable_type_filter", "BOOL", enable_entity_type_filter),
            bigquery.ArrayQueryParameter("allowed_types", "STRING", allowed_entity_types),
        ]
        row = next(iter(self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()))
        return {
            "docs_total": int(row.docs_total or 0),
            "docs_paper": int(row.docs_paper or 0),
            "docs_trial": int(row.docs_trial or 0),
            "docs_patent": int(row.docs_patent or 0),
            "min_linked_entities": min_linked_entities,
            "enable_entity_type_filter": enable_entity_type_filter,
            "allowed_entity_types": allowed_entity_types,
        }

    def iter_filtered_docs(
        self,
        min_linked_entities: int,
        enable_entity_type_filter: bool = False,
        allowed_entity_types: list[str] | None = None,
        start_after_doc_id: str = "",
    ) -> Iterator[EvidenceDoc]:
        allowed_entity_types = [t.lower() for t in (allowed_entity_types or [])]
        query = f"""
        WITH docs AS (
          {self._docs_union_sql()}
        ),
        links AS (
          {self._link_union_sql()}
        ),
        filtered_links AS (
          SELECT * FROM links
          WHERE entity_id IS NOT NULL
            AND (@enable_type_filter = FALSE OR entity_type IN UNNEST(@allowed_types))
        ),
        doc_counts AS (
          SELECT doc_id, doc_type, COUNT(DISTINCT entity_id) AS entity_count
          FROM filtered_links
          GROUP BY doc_id, doc_type
        )
        SELECT d.doc_id, d.doc_type, d.source_id, d.text, c.entity_count
        FROM docs d
        JOIN doc_counts c USING (doc_id, doc_type)
        WHERE c.entity_count >= @min_linked_entities
          AND d.doc_id > @start_after_doc_id
        ORDER BY d.doc_id
        """
        params = [
            bigquery.ScalarQueryParameter("min_linked_entities", "INT64", min_linked_entities),
            bigquery.ScalarQueryParameter("enable_type_filter", "BOOL", enable_entity_type_filter),
            bigquery.ArrayQueryParameter("allowed_types", "STRING", allowed_entity_types),
            bigquery.ScalarQueryParameter("start_after_doc_id", "STRING", start_after_doc_id),
        ]
        rows = self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result(page_size=2000)
        for r in rows:
            yield EvidenceDoc(r.doc_id, r.doc_type, r.source_id, r.text, int(r.entity_count or 0))

    def fetch_doc_entities(self, doc_ids: Iterable[str]) -> list[DocEntity]:
        doc_ids = list(doc_ids)
        if not doc_ids:
            return []
        query = f"""
        DECLARE target_doc_ids ARRAY<STRING> DEFAULT @doc_ids;

        WITH paper AS (
          SELECT CONCAT('PMID:', CAST(PMID AS STRING)) AS doc_id,
                 COALESCE(NULLIF(NCBIGene, ''), NULLIF(CHEBI, ''), NULLIF(mesh, ''), NULLIF(EntityId, '')) AS raw_entity,
                 Type AS entity_type,
                 Mention AS mention,
                 'C06_Link_Papers_BioEntities' AS source_table
          FROM {self._fq_source(SETTINGS.source_table_c06)}
        ),
        trial AS (
          SELECT CONCAT('NCT:', nct_id) AS doc_id,
                 COALESCE(NULLIF(NCBIGene, ''), NULLIF(CHEBI, ''), NULLIF(mesh, ''), NULLIF(EntityId, '')) AS raw_entity,
                 Type AS entity_type,
                 Mention AS mention,
                 'C13_Link_ClinicalTrials_BioEntities' AS source_table
          FROM {self._fq_source(SETTINGS.source_table_c13)}
        ),
        patent AS (
          SELECT CONCAT('PATENT:', PatentId) AS doc_id,
                 COALESCE(NULLIF(NCBIGene, ''), NULLIF(CHEBI, ''), NULLIF(mesh, ''), NULLIF(EntityId, '')) AS raw_entity,
                 Type AS entity_type,
                 Mention AS mention,
                 'C18_Link_Patents_BioEntities' AS source_table
          FROM {self._fq_source(SETTINGS.source_table_c18)}
        ),
        all_links AS (
          SELECT * FROM paper
          UNION ALL SELECT * FROM trial
          UNION ALL SELECT * FROM patent
        )
        SELECT doc_id, raw_entity AS entity_id, entity_type, mention, source_table
        FROM all_links
        WHERE doc_id IN UNNEST(target_doc_ids)
          AND raw_entity IS NOT NULL
        """
        params = [bigquery.ArrayQueryParameter("doc_ids", "STRING", doc_ids)]
        rows = self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return [DocEntity(r.doc_id, r.entity_id, r.entity_type, r.mention, r.source_table) for r in rows]

    def insert_rows(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        errors = self.client.insert_rows_json(f"{self.project_id}.{self.target_dataset}.{table}", rows)
        if errors:
            raise RuntimeError(f"Failed inserts into {table}: {errors[:3]}")

    def get_candidate_chunks_for_nodes(self, node_a: str, node_b: str, limit: int = 2000) -> list[dict]:
        query = f"""
        WITH candidate_docs AS (
          SELECT doc_id
          FROM {self._fq_target('evidence_doc_entities_pilot')}
          WHERE entity_id IN (@node_a, @node_b)
          GROUP BY doc_id
          HAVING COUNT(DISTINCT entity_id) = 2
        )
        SELECT c.chunk_id, c.doc_id, c.doc_type, c.chunk_text, c.embedding, c.source_id
        FROM {self._fq_target('evidence_embeddings_pilot')} c
        JOIN candidate_docs d USING (doc_id)
        LIMIT @limit
        """
        params = [
            bigquery.ScalarQueryParameter("node_a", "STRING", node_a),
            bigquery.ScalarQueryParameter("node_b", "STRING", node_b),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
        rows = self.client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return [dict(r.items()) for r in rows]
