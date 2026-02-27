import logging

from fastapi import APIRouter, HTTPException

from backend.models.request import QueryRequest
from backend.models.response import JsonGraphPayload
from backend.services.gemini import extract_entity
from backend.services.bigquery import (
    find_entity,
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
