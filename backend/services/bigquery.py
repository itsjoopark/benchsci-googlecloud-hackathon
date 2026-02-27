import asyncio
import logging
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account

from backend.config import settings

logger = logging.getLogger(__name__)

_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        kwargs: dict = {
            "project": settings.GCP_PROJECT_ID,
            "location": settings.GCP_REGION,
        }
        # Use service account key if available for BQ auth
        sa_path = Path(settings.SERVICE_ACCOUNT_KEY_PATH)
        if sa_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(sa_path)
            )
            kwargs["credentials"] = credentials
            logger.info("Using service account key for BigQuery: %s", sa_path)
        _client = bigquery.Client(**kwargs)
    return _client


def _table(name: str) -> str:
    return f"`{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.{name}`"


async def find_entity(
    query: str, entity_type: str | None = None
) -> dict | None:
    """Find the best-matching entity in C23_BioEntities."""
    type_filter = ""
    params = [bigquery.ScalarQueryParameter("query", "STRING", query)]

    if entity_type:
        type_filter = "AND LOWER(Type) = LOWER(@entity_type)"
        params.append(
            bigquery.ScalarQueryParameter("entity_type", "STRING", entity_type)
        )

    sql = f"""
    SELECT EntityId, Type, Mention,
      CASE
        WHEN LOWER(Mention) = LOWER(@query) THEN 1
        WHEN LOWER(Mention) LIKE CONCAT(LOWER(@query), '%') THEN 2
        WHEN LOWER(Mention) LIKE CONCAT('%', LOWER(@query), '%') THEN 3
        WHEN LOWER(EntityId) LIKE CONCAT('%', LOWER(@query), '%') THEN 4
        ELSE 5
      END AS match_rank
    FROM {_table("C23_BioEntities")}
    WHERE (
      LOWER(Mention) LIKE CONCAT('%', LOWER(@query), '%')
      OR LOWER(EntityId) LIKE CONCAT('%', LOWER(@query), '%')
    )
    {type_filter}
    ORDER BY match_rank ASC, LENGTH(Mention) ASC
    LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client = _get_client()

    rows = await asyncio.to_thread(
        lambda: list(client.query(sql, job_config=job_config).result())
    )

    if not rows:
        # Retry without type filter if we had one
        if entity_type:
            logger.info(
                "No results with type filter '%s', retrying without", entity_type
            )
            return await find_entity(query, entity_type=None)
        return None

    row = rows[0]
    return {
        "entity_id": row["EntityId"],
        "type": row["Type"],
        "mention": row["Mention"],
    }


async def find_related_entities(entity_id: str) -> list[dict]:
    """Find entities related to the given entity via C21_Bioentity_Relationships,
    ranked by combined co-occurrence across papers, clinical trials, and patents."""
    sql = f"""
    WITH
    -- C21 relationships for the seed entity
    relationships AS (
      SELECT entity_id1, entity_id2, relation_type, PMID,
        CASE WHEN entity_id1 = @entity_id THEN entity_id2 ELSE entity_id1 END AS other_entity_id,
        CASE WHEN entity_id1 = @entity_id THEN '->' ELSE '<-' END AS direction
      FROM {_table("C21_Bioentity_Relationships")}
      WHERE entity_id1 = @entity_id OR entity_id2 = @entity_id
    ),
    agg AS (
      SELECT other_entity_id, relation_type, direction,
        COUNT(DISTINCT PMID) AS evidence_count,
        ARRAY_AGG(DISTINCT PMID ORDER BY PMID LIMIT {settings.MAX_EVIDENCE_PER_EDGE}) AS pmids
      FROM relationships
      GROUP BY other_entity_id, relation_type, direction
    ),

    -- Co-occurrence: papers (C06)
    paper_co AS (
      SELECT a.Entityid AS other_entity_id, COUNT(DISTINCT a.PMID) AS paper_count
      FROM {_table("C06_Link_Papers_BioEntities")} seed
      JOIN {_table("C06_Link_Papers_BioEntities")} a ON a.PMID = seed.PMID
      WHERE seed.Entityid = @entity_id
        AND a.Entityid != @entity_id
      GROUP BY a.Entityid
    ),

    -- Co-occurrence: clinical trials (C13)
    trial_co AS (
      SELECT a.EntityId AS other_entity_id, COUNT(DISTINCT a.nct_id) AS trial_count
      FROM {_table("C13_Link_ClinicalTrials_BioEntities")} seed
      JOIN {_table("C13_Link_ClinicalTrials_BioEntities")} a ON a.nct_id = seed.nct_id
      WHERE seed.EntityId = @entity_id
        AND a.EntityId != @entity_id
      GROUP BY a.EntityId
    ),

    -- Co-occurrence: patents (C18)
    patent_co AS (
      SELECT a.EntityId AS other_entity_id, COUNT(DISTINCT a.PatentId) AS patent_count
      FROM {_table("C18_Link_Patents_BioEntities")} seed
      JOIN {_table("C18_Link_Patents_BioEntities")} a ON a.PatentId = seed.PatentId
      WHERE seed.EntityId = @entity_id
        AND a.EntityId != @entity_id
      GROUP BY a.EntityId
    )

    SELECT
      a.*,
      e.Type  AS other_type,
      e.Mention AS other_mention,
      COALESCE(pc.paper_count,  0) AS paper_count,
      COALESCE(tc.trial_count,  0) AS trial_count,
      COALESCE(pt.patent_count, 0) AS patent_count,
      COALESCE(pc.paper_count,  0)
        + COALESCE(tc.trial_count,  0)
        + COALESCE(pt.patent_count, 0) AS cooccurrence_score
    FROM agg a
    LEFT JOIN {_table("C23_BioEntities")} e   ON e.EntityId        = a.other_entity_id
    LEFT JOIN paper_co  pc                    ON pc.other_entity_id = a.other_entity_id
    LEFT JOIN trial_co  tc                    ON tc.other_entity_id = a.other_entity_id
    LEFT JOIN patent_co pt                    ON pt.other_entity_id = a.other_entity_id
    ORDER BY cooccurrence_score DESC, a.evidence_count DESC
    LIMIT {settings.MAX_RELATED_ENTITIES}
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("entity_id", "STRING", entity_id),
        ]
    )
    client = _get_client()

    rows = await asyncio.to_thread(
        lambda: list(client.query(sql, job_config=job_config).result())
    )

    return [
        {
            "other_entity_id": row["other_entity_id"],
            "relation_type": row["relation_type"],
            "direction": row["direction"],
            "evidence_count": row["evidence_count"],
            "pmids": [str(p) for p in row["pmids"]] if row["pmids"] else [],
            "other_type": row["other_type"],
            "other_mention": row["other_mention"],
            "paper_count": row["paper_count"],
            "trial_count": row["trial_count"],
            "patent_count": row["patent_count"],
            "cooccurrence_score": row["cooccurrence_score"],
        }
        for row in rows
    ]


async def fetch_paper_details(pmids: list[str]) -> dict[str, dict]:
    """Batch lookup paper titles and years from C01_Papers."""
    if not pmids:
        return {}

    # PMID column is INT64 in BigQuery — cast string PMIDs to integers
    int_pmids = []
    for p in pmids:
        try:
            int_pmids.append(int(p))
        except (ValueError, TypeError):
            continue

    if not int_pmids:
        return {}

    sql = f"""
    SELECT PMID, ArticleTitle, PubYear
    FROM {_table("C01_Papers")}
    WHERE PMID IN UNNEST(@pmids)
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("pmids", "INT64", int_pmids),
        ]
    )
    client = _get_client()

    rows = await asyncio.to_thread(
        lambda: list(client.query(sql, job_config=job_config).result())
    )

    return {
        str(row["PMID"]): {
            "title": row["ArticleTitle"] or "",
            "year": int(row["PubYear"]) if row["PubYear"] else 0,
        }
        for row in rows
    }
