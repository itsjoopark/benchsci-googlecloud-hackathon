import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.models.deep_think import DeepThinkChatRequest, DeepThinkRequest
from backend.models.overview import OverviewStreamRequest
from backend.models.request import QueryRequest, ExpandRequest
from backend.models.response import JsonGraphPayload
from backend.services.gemini import extract_entity
from backend.services.deep_think import stream_deep_think_chat_events, stream_deep_think_events
from backend.services.overview import stream_overview_events, verify_vector_overview
from backend.services.bigquery import (
    find_entity,
    find_entity_by_id,
    find_related_entities,
    fetch_paper_details,
)
from backend.services.graph_builder import build_graph_payload, build_not_found_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/query", response_model=JsonGraphPayload)
async def query_entity(request: QueryRequest) -> JsonGraphPayload:
    # Step 1: Extract entity from natural language query
    try:
        extracted = await extract_entity(request.query)
        logger.info("Extracted entity: %s", extracted)
    except Exception as e:
        logger.error("Gemini extraction failed: %s", e)
        raise HTTPException(status_code=502, detail="Entity extraction failed") from e

    # Step 2: Look up entity in BigQuery
    entity = await find_entity(
        extracted.entity_name,
        entity_type=extracted.entity_type,
    )
    if not entity:
        return build_not_found_response(extracted.entity_name)

    # Step 3: Find related entities
    related = await find_related_entities(entity["entity_id"])

    # Step 4: Collect all PMIDs and batch-fetch paper details
    all_pmids: list[str] = []
    for rel in related:
        all_pmids.extend(rel.get("pmids", []))
    unique_pmids = list(set(all_pmids))

    paper_details = await fetch_paper_details(unique_pmids)

    # Step 5: Build graph payload
    payload = build_graph_payload(entity, related, paper_details)
    return payload


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
