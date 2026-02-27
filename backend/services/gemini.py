import asyncio
import json
import logging

from gradio_client import Client

from backend.config import settings
from backend.models.gemini import ExtractedEntity

logger = logging.getLogger(__name__)

def _create_client() -> Client:
    url = settings.GEMINI_ENDPOINT_URL.rstrip("/")
    kwargs = {}
    if settings.GEMINI_APP_KEY:
        # Append app key to every request to the deployed extraction app.
        kwargs["httpx_kwargs"] = {"params": {"key": settings.GEMINI_APP_KEY}}
    return Client(url, **kwargs)


async def extract_entity(query: str) -> ExtractedEntity:
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
