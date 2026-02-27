import asyncio
import json
import logging
import re

from google import genai
from google.genai import types as genai_types
from gradio_client import Client

from backend.config import settings
from backend.models.gemini import ExtractedEntity, ExtractedEntityPair

logger = logging.getLogger(__name__)
_fallback_client: genai.Client | None = None

def _create_client() -> Client:
    url = settings.GEMINI_ENDPOINT_URL.rstrip("/")
    kwargs = {}
    if settings.GEMINI_APP_KEY:
        # Append app key to every request to the deployed extraction app.
        kwargs["httpx_kwargs"] = {"params": {"key": settings.GEMINI_APP_KEY}}
    return Client(url, **kwargs)


def _get_fallback_client() -> genai.Client:
    global _fallback_client
    if _fallback_client is None:
        _fallback_client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location="global",
        )
    return _fallback_client


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _is_plausible_entity_for_query(entity_name: str, query: str) -> bool:
    if not entity_name.strip() or not query.strip():
        return False
    q = _normalize_text(query)
    e = _normalize_text(entity_name)
    if not q or not e:
        return False
    if q in e or e in q:
        return True
    # Fuzzy guard for multi-word inputs
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
    e_tokens = {t for t in re.findall(r"[a-z0-9]+", entity_name.lower()) if len(t) > 2}
    return len(q_tokens & e_tokens) > 0


async def _extract_entity_via_app(query: str) -> ExtractedEntity:
    client = _create_client()

    # gradio_client.predict is synchronous — run in thread to avoid blocking
    raw = await asyncio.to_thread(
        client.predict,
        message={"text": query, "files": []},
        api_name="/chat",
    )

    logger.info("Gemini extraction result: %s", raw)

    # The Gradio app may return:
    # - A list of streaming chunks (join them first)
    # - A string directly
    # The content may be wrapped in {"response": "..."} with escaped JSON
    if isinstance(raw, list):
        text = "".join(raw)
    else:
        text = str(raw)

    text = text.strip()

    # Try parsing as-is first; if it has a "response" wrapper, unwrap it
    try:
        outer = json.loads(text)
        if isinstance(outer, dict) and "response" in outer:
            text = outer["response"]
        else:
            # Already valid JSON with entity fields
            return ExtractedEntity(**outer)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    parsed = json.loads(text)
    return ExtractedEntity(**parsed)


async def _extract_entity_via_fallback(query: str) -> ExtractedEntity:
    prompt = f"""
Extract exactly one primary biomedical entity from the user query.
Return only JSON with this shape:
{{
  "entity_name": "<string>",
  "entity_type": "<gene|disease|drug|pathway|protein|other>",
  "qualifiers": ["<string>", ...]
}}
Rules:
- entity_name must be the most salient single entity in the query.
- qualifiers can be empty.
- no markdown, no explanation.
User query: {query}
""".strip()

    client = _get_fallback_client()
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-3-flash-preview",
        contents=[
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=prompt)],
            )
        ],
        config=genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=200,
            response_mime_type="application/json",
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )
    payload = json.loads((response.text or "").strip())
    return ExtractedEntity(**payload)


async def extract_entity(query: str) -> ExtractedEntity:
    try:
        extracted = await _extract_entity_via_app(query)
        if _is_plausible_entity_for_query(extracted.entity_name, query):
            return extracted
        logger.warning(
            "App extraction appears stale/mismatched (query=%r, entity=%r); using fallback",
            query,
            extracted.entity_name,
        )
    except Exception as exc:
        logger.warning("App extraction failed for query=%r; using fallback: %s", query, exc)

    return await _extract_entity_via_fallback(query)


# ---------------------------------------------------------------------------
# Gemini function-calling based intent detection
# ---------------------------------------------------------------------------

_SEARCH_ENTITY_FUNC = genai_types.FunctionDeclaration(
    name="search_entity",
    description=(
        "Search for a single biomedical entity (gene, disease, drug, pathway, "
        "or protein) and show its neighborhood graph."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "entity_name": {
                "type": "string",
                "description": "The canonical / most common name of the biomedical entity",
            },
            "entity_type": {
                "type": "string",
                "enum": ["gene", "disease", "drug", "pathway", "protein"],
                "description": "The type of the biomedical entity",
            },
        },
        "required": ["entity_name", "entity_type"],
    },
)

_FIND_SHORTEST_PATH_FUNC = genai_types.FunctionDeclaration(
    name="find_shortest_path",
    description=(
        "Find the shortest path connecting two biomedical entities in the "
        "knowledge graph. Use when the user mentions two entities and wants to "
        "understand their connection or relationship."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "entity1_name": {
                "type": "string",
                "description": "Canonical name of the first entity",
            },
            "entity1_type": {
                "type": "string",
                "enum": ["gene", "disease", "drug", "pathway", "protein"],
                "description": "Type of the first entity",
            },
            "entity2_name": {
                "type": "string",
                "description": "Canonical name of the second entity",
            },
            "entity2_type": {
                "type": "string",
                "enum": ["gene", "disease", "drug", "pathway", "protein"],
                "description": "Type of the second entity",
            },
        },
        "required": ["entity1_name", "entity1_type", "entity2_name", "entity2_type"],
    },
)

_BIOMEDICAL_TOOLS = genai_types.Tool(
    function_declarations=[_SEARCH_ENTITY_FUNC, _FIND_SHORTEST_PATH_FUNC],
)

_SYSTEM_INSTRUCTION = (
    "You are a biomedical entity parser. The user will provide a query about "
    "biomedical entities. Call the appropriate function based on whether the user "
    "is searching for one entity or looking for a connection between two entities. "
    "Always use the most common canonical name for each entity."
)


async def extract_query_intent(query: str) -> tuple[str, dict]:
    """Use Gemini function calling to determine query intent.

    Returns ``(function_name, arguments)`` where *function_name* is either
    ``"search_entity"`` or ``"find_shortest_path"`` and *arguments* is the
    dict of parameters chosen by Gemini.
    """
    client = _get_fallback_client()

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.GEMINI_OVERVIEW_MODEL,
        contents=[
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=query)],
            )
        ],
        config=genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=200,
            tools=[_BIOMEDICAL_TOOLS],
            system_instruction=_SYSTEM_INSTRUCTION,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )

    # Extract the function call from the response
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if part.function_call:
                return (part.function_call.name, dict(part.function_call.args))

    raise ValueError("Gemini did not return a function call")
