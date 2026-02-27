"""Cloud Spanner Graph service for shortest-path queries.

Strategy:
  1. Try GQL ``ANY SHORTEST`` for 1-hop direct paths (instant).
  2. Fall back to bidirectional BFS using fast Spanner neighbor lookups
     (~50-100 ms per hop vs ~1-2 s per BigQuery round-trip).
"""

import asyncio
import logging
from pathlib import Path

from google.cloud import spanner
from google.oauth2 import service_account

from backend.config import settings

logger = logging.getLogger(__name__)

_client: spanner.Client | None = None
_database = None

MAX_DEPTH = 4  # Max hops per BFS direction (total path length up to ~8)
MAX_FRONTIER_SIZE = 500  # Cap frontier to prevent hub-node explosion


def _get_database():
    """Lazy-init the Spanner client -> instance -> database handle."""
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


# ---------------------------------------------------------------------------
# GQL direct-path check (1-hop, instant)
# ---------------------------------------------------------------------------

async def _try_direct_path(start_id: str, end_id: str) -> list[dict] | None:
    """Try to find a direct 1-hop path via GQL ANY SHORTEST."""
    gql = """
    GRAPH BioGraph
    MATCH p = ANY SHORTEST
      (src:BioEntity WHERE src.entity_id = @start_id)
      -[e:Relationship]->{1,1}
      (dst:BioEntity WHERE dst.entity_id = @end_id)
    RETURN
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
            return list(results)

    try:
        rows = await asyncio.to_thread(_execute)
    except Exception:
        logger.exception("Spanner GQL direct-path query failed")
        return None

    if not rows:
        return None

    edges_data = rows[0][0]
    segments = []
    for edge in edges_data:
        segments.append({
            "from": edge[0],
            "to": edge[1],
            "relation_type": edge[2],
        })
    return segments


# ---------------------------------------------------------------------------
# Spanner-backed neighbor lookup for BFS
# ---------------------------------------------------------------------------

async def _find_neighbor_ids(entity_ids: list[str]) -> dict[str, list[dict]]:
    """Batch 1-hop neighbor lookup via Spanner SQL.

    Uses the primary key index (entity_id1) for forward lookups and the
    BioRelationship_Reverse secondary index (entity_id2) for reverse lookups.

    Returns ``{src: [{neighbor_id, relation_type}]}``.
    """
    if not entity_ids:
        return {}

    database = _get_database()

    # Since we store edges bidirectionally, we only need the forward direction
    # (entity_id1 -> entity_id2) to find all neighbors.
    sql = """
    SELECT entity_id1 AS src, entity_id2 AS nbr, relation_type
    FROM BioRelationship
    WHERE entity_id1 IN UNNEST(@ids)
    """

    def _execute():
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                sql,
                params={"ids": entity_ids},
                param_types={"ids": spanner.param_types.Array(spanner.param_types.STRING)},
            )
            return list(results)

    rows = await asyncio.to_thread(_execute)

    result: dict[str, list[dict]] = {}
    for row in rows:
        src = row[0]
        if src not in result:
            result[src] = []
        result[src].append({
            "neighbor_id": row[1],
            "relation_type": row[2],
        })
    return result


# ---------------------------------------------------------------------------
# Bidirectional BFS using Spanner neighbor lookups
# ---------------------------------------------------------------------------

async def _bfs_shortest_path(start_id: str, end_id: str) -> list[dict] | None:
    """Bidirectional BFS using fast Spanner neighbor reads."""
    # parent maps: entity_id -> (parent_id | None, relation_type | None)
    forward_parents: dict[str, tuple[str | None, str | None]] = {
        start_id: (None, None)
    }
    forward_frontier: set[str] = {start_id}

    backward_parents: dict[str, tuple[str | None, str | None]] = {
        end_id: (None, None)
    }
    backward_frontier: set[str] = {end_id}

    for depth in range(MAX_DEPTH):
        if len(forward_frontier) <= len(backward_frontier):
            meeting = await _expand_frontier(
                forward_frontier, forward_parents, backward_parents
            )
            if meeting is not None:
                return _reconstruct_path(meeting, forward_parents, backward_parents)
            if not forward_frontier:
                return None
        else:
            meeting = await _expand_frontier(
                backward_frontier, backward_parents, forward_parents
            )
            if meeting is not None:
                return _reconstruct_path(meeting, forward_parents, backward_parents)
            if not backward_frontier:
                return None

    return None


async def _expand_frontier(
    frontier: set[str],
    own_parents: dict[str, tuple[str | None, str | None]],
    other_parents: dict[str, tuple[str | None, str | None]],
) -> str | None:
    """Expand *frontier* one BFS level using Spanner neighbor lookups."""
    frontier_list = list(frontier)
    if len(frontier_list) > MAX_FRONTIER_SIZE:
        frontier_list = frontier_list[:MAX_FRONTIER_SIZE]

    neighbors = await _find_neighbor_ids(frontier_list)

    new_frontier: set[str] = set()
    for src in frontier_list:
        for nbr in neighbors.get(src, []):
            nid = nbr["neighbor_id"]
            if nid in own_parents:
                continue
            own_parents[nid] = (src, nbr["relation_type"])
            new_frontier.add(nid)

            if nid in other_parents:
                frontier.clear()
                frontier.update(new_frontier)
                return nid

    frontier.clear()
    frontier.update(new_frontier)
    return None


def _reconstruct_path(
    meeting_point: str,
    forward_parents: dict[str, tuple[str | None, str | None]],
    backward_parents: dict[str, tuple[str | None, str | None]],
) -> list[dict]:
    """Trace back from the meeting point through both parent maps."""
    # Forward half: start -> meeting_point
    forward_path: list[dict] = []
    current = meeting_point
    while forward_parents[current][0] is not None:
        parent, rel_type = forward_parents[current]
        forward_path.append({
            "from": parent,
            "to": current,
            "relation_type": rel_type,
        })
        current = parent  # type: ignore[assignment]
    forward_path.reverse()

    # Backward half: meeting_point -> end
    backward_path: list[dict] = []
    current = meeting_point
    while backward_parents[current][0] is not None:
        parent, rel_type = backward_parents[current]
        backward_path.append({
            "from": current,
            "to": parent,
            "relation_type": rel_type,
        })
        current = parent  # type: ignore[assignment]

    return forward_path + backward_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def find_shortest_path_spanner(
    start_id: str, end_id: str, max_hops: int = 8
) -> list[dict] | None:
    """Find shortest path between two entities using Spanner.

    Strategy:
      1. Try GQL ``ANY SHORTEST`` for a direct 1-hop path (instant).
      2. Fall back to bidirectional BFS with Spanner neighbor lookups
         (~50-100 ms per hop vs ~1-2 s with BigQuery).

    Returns:
        List of path segments ``[{"from": id, "to": id, "relation_type": str}]``,
        or ``None`` if no path exists within *max_hops*.
        Returns ``[]`` if start == end.
    """
    if start_id == end_id:
        return []

    # Fast path: try GQL for direct 1-hop connection
    direct = await _try_direct_path(start_id, end_id)
    if direct is not None:
        logger.info("Found direct 1-hop path via GQL: %s -> %s", start_id, end_id)
        return direct

    # Fall back to BFS with Spanner neighbor lookups
    logger.info("No direct path; running BFS via Spanner: %s -> %s", start_id, end_id)
    return await _bfs_shortest_path(start_id, end_id)
