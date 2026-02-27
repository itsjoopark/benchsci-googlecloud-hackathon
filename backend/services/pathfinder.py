"""Shortest-path finder — delegates to Cloud Spanner Graph."""

import logging

from backend.services.spanner import find_shortest_path_spanner

logger = logging.getLogger(__name__)


async def find_shortest_path(
    start_id: str, end_id: str
) -> list[dict] | None:
    """Find the shortest path between two entities.

    Delegates to Spanner Graph's ``ANY SHORTEST`` GQL query for single-round-trip
    path finding.  The return format is unchanged from the previous BFS implementation:

        [{"from": id, "to": id, "relation_type": str}, ...]

    Note: PMIDs are no longer included in the path segments — they are fetched
    separately from BigQuery via ``fetch_edge_pmids()`` in the query router.

    Returns ``None`` if no path is found, or ``[]`` if start == end.
    """
    return await find_shortest_path_spanner(start_id, end_id)
