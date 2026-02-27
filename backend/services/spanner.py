"""Cloud Spanner Graph service for shortest-path queries using GQL."""

import asyncio
import logging
from pathlib import Path

from google.cloud import spanner
from google.oauth2 import service_account

from backend.config import settings

logger = logging.getLogger(__name__)

_client: spanner.Client | None = None
_database = None


def _get_database():
    """Lazy-init the Spanner client → instance → database handle."""
    global _client, _database
    if _database is None:
        kwargs: dict = {"project": settings.GCP_PROJECT_ID}
        sa_path = Path(settings.SERVICE_ACCOUNT_KEY_PATH)
        if sa_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(sa_path),
                scopes=["https://www.googleapis.com/auth/spanner.data"],
            )
            kwargs["credentials"] = credentials
            logger.info("Using service account key for Spanner: %s", sa_path)
        _client = spanner.Client(**kwargs)
        instance = _client.instance(settings.SPANNER_INSTANCE_ID)
        _database = instance.database(settings.SPANNER_DATABASE_ID)
    return _database


async def find_shortest_path_spanner(
    start_id: str, end_id: str, max_hops: int = 8
) -> list[dict] | None:
    """Find shortest path between two entities using Spanner Graph GQL.

    Uses the ``ANY SHORTEST`` GQL operator for single-query path finding
    instead of iterative BFS round-trips.

    Returns:
        List of path segments ``[{"from": id, "to": id, "relation_type": str}]``,
        or ``None`` if no path exists within *max_hops*.
        Returns ``[]`` if start == end.
    """
    if start_id == end_id:
        return []

    # Use undirected edge pattern (-[e:Relationship]-) since the knowledge graph
    # stores relationships as entity_id1 -> entity_id2 but traversal should be
    # bidirectional (e.g., A->B stored once but path B->A is valid).
    gql = f"""
    GRAPH BioGraph
    MATCH p = ANY SHORTEST
      (src:BioEntity WHERE src.entity_id = @start_id)
      -[e:Relationship]-{{1,{max_hops}}}
      (dst:BioEntity WHERE dst.entity_id = @end_id)
    RETURN
      ARRAY(SELECT AS STRUCT n.entity_id FROM UNNEST(NODES(p)) AS n) AS nodes,
      ARRAY(SELECT AS STRUCT
              e.entity_id1 AS `from`,
              e.entity_id2 AS `to`,
              e.relation_type
            FROM UNNEST(EDGES(p)) AS e) AS edges
    """

    database = _get_database()

    def _execute():
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                gql,
                params={"start_id": start_id, "end_id": end_id},
                param_types={
                    "start_id": spanner.param_types.STRING,
                    "end_id": spanner.param_types.STRING,
                },
            )
            rows = list(results)
            return rows

    try:
        rows = await asyncio.to_thread(_execute)
    except Exception:
        logger.exception("Spanner GQL query failed for %s -> %s", start_id, end_id)
        return None

    if not rows:
        return None

    # Parse the first (only) result row
    row = rows[0]
    edges_data = row[1]  # Second column: edges array of structs

    path_segments = []
    for edge in edges_data:
        path_segments.append({
            "from": edge[0],   # entity_id1
            "to": edge[1],     # entity_id2
            "relation_type": edge[2],
        })

    return path_segments
