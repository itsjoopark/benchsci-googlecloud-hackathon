import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.models.deep_think import DeepThinkChatRequest, DeepThinkRequest
from backend.models.overview import OverviewStreamRequest
from backend.models.request import QueryRequest, ExpandRequest
from backend.models.response import JsonGraphPayload
from backend.services.gemini import extract_entity, extract_query_intent
from backend.services.deep_think import stream_deep_think_chat_events, stream_deep_think_events
from backend.services.overview import stream_overview_events, verify_vector_overview
from backend.services.bigquery import (
    find_entity,
    find_entity_by_id,
    find_entities_by_ids,
    find_related_entities,
    fetch_paper_details,
    fetch_edge_pmids,
)
from backend.services.graph_builder import (
    build_graph_payload,
    build_path_graph_payload,
    build_not_found_response,
)
from backend.services.pathfinder import find_shortest_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/query", response_model=JsonGraphPayload)
async def query_entity(request: QueryRequest) -> JsonGraphPayload:
    # Step 1: Use Gemini function calling to determine intent
    try:
        func_name, args = await extract_query_intent(request.query)
        logger.info("Gemini intent: func=%s args=%s", func_name, args)
    except Exception as e:
        # Fallback to existing single-entity extraction
        logger.warning("Intent extraction failed (%s), falling back to single-entity", e)
        try:
            extracted = await extract_entity(request.query)
            func_name = "search_entity"
            args = {"entity_name": extracted.entity_name, "entity_type": extracted.entity_type}
        except Exception as e2:
            logger.error("Fallback extraction also failed: %s", e2)
            raise HTTPException(status_code=502, detail="Entity extraction failed") from e2

    # Step 2: Dispatch based on function call
    if func_name == "find_shortest_path":
        return await _handle_shortest_path(args)
    else:
        return await _handle_search_entity(args)


async def _handle_search_entity(args: dict) -> JsonGraphPayload:
    """Existing single-entity search flow."""
    entity = await find_entity(
        args.get("entity_name", ""),
        entity_type=args.get("entity_type"),
    )
    if not entity:
        return build_not_found_response(args.get("entity_name", ""))

    related = await find_related_entities(entity["entity_id"])

    all_pmids: list[str] = []
    for rel in related:
        all_pmids.extend(rel.get("pmids", []))
    paper_details = await fetch_paper_details(list(set(all_pmids)))

    return build_graph_payload(entity, related, paper_details)


async def _handle_shortest_path(args: dict) -> JsonGraphPayload:
    """Find and return the shortest path between two entities."""
    name1 = args.get("entity1_name", "")
    type1 = args.get("entity1_type")
    name2 = args.get("entity2_name", "")
    type2 = args.get("entity2_type")

    if not name1 or not name2:
        return build_not_found_response("Could not identify two entities in the query.")

    # Look up both entities in BigQuery
    entity1 = await find_entity(name1, entity_type=type1)
    if not entity1:
        return build_not_found_response(name1)

    entity2 = await find_entity(name2, entity_type=type2)
    if not entity2:
        return build_not_found_response(name2)

    id1 = entity1["entity_id"]
    id2 = entity2["entity_id"]

    if id1 == id2:
        return JsonGraphPayload(
            center_node_id=id1,
            nodes=[],
            edges=[],
            message=f"'{name1}' and '{name2}' resolve to the same entity.",
        )

    # Find shortest path via Spanner Graph (single GQL query)
    path_segments = await find_shortest_path(id1, id2)

    if path_segments is None:
        return JsonGraphPayload(
            center_node_id=id1,
            nodes=[],
            edges=[],
            message=f"No path found between '{name1}' and '{name2}' within the knowledge graph.",
        )

    # Collect all entity IDs along the path
    path_ids = [id1]
    for seg in path_segments:
        if seg["to"] not in path_ids:
            path_ids.append(seg["to"])

    # Fetch PMIDs for path edges from BigQuery (Spanner returns structure only)
    edge_pairs = [(seg["from"], seg["to"], seg["relation_type"]) for seg in path_segments]
    edge_pmids = await fetch_edge_pmids(edge_pairs)

    # Enrich path segments with PMIDs
    for seg in path_segments:
        key = f"{seg['from']}--{seg['to']}--{seg['relation_type']}"
        seg["pmids"] = edge_pmids.get(key, [])

    # Batch-fetch entity details and paper details
    entity_details = await find_entities_by_ids(path_ids)
    all_pmids: list[str] = [p for seg in path_segments for p in seg.get("pmids", [])]
    paper_details = await fetch_paper_details(list(set(all_pmids)))

    return build_path_graph_payload(path_ids, path_segments, entity_details, paper_details)


@router.post("/expand", response_model=JsonGraphPayload)
async def expand_entity(request: ExpandRequest) -> JsonGraphPayload:
    # Step 1: Look up entity by exact ID
    entity = await find_entity_by_id(request.entity_id)
    if not entity:
        return build_not_found_response(request.entity_id)

    # Step 2: Find related entities
    related = await find_related_entities(entity["entity_id"])

    # Step 3: Batch-fetch paper details
    all_pmids: list[str] = []
    for rel in related:
        all_pmids.extend(rel.get("pmids", []))
    unique_pmids = list(set(all_pmids))

    paper_details = await fetch_paper_details(unique_pmids)

    # Step 4: Build graph payload
    return build_graph_payload(entity, related, paper_details)


@router.post("/overview/stream")
async def stream_overview(request: OverviewStreamRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_overview_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/overview/verify")
async def verify_overview_vector() -> dict:
    return verify_vector_overview()


@router.post("/deep-think/stream")
async def stream_deep_think(request: DeepThinkRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_deep_think_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/deep-think/chat/stream")
async def stream_deep_think_chat(request: DeepThinkChatRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_deep_think_chat_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
