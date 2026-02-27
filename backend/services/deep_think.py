from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Iterator

from google.genai import types as genai_types

from backend.config import settings
from backend.models.deep_think import DeepThinkEdge, DeepThinkPathNode, DeepThinkRequest
from backend.services.overview import _get_genai_client

logger = logging.getLogger(__name__)

_MAX_PMIDS = 15


def _extract_weighted_pmids(
    path: list[DeepThinkPathNode],
    edges: list[DeepThinkEdge],
) -> list[tuple[str, float]]:
    """Return deduplicated (pmid, weight) pairs sorted by weight descending.

    The last pair in the path (most recently added) gets i=0 → weight 1.0.
    """
    pairs = list(zip(path[:-1], path[1:]))
    pmid_weights: dict[str, float] = {}

    for i, (src_node, tgt_node) in enumerate(reversed(pairs)):
        weight = 1.0 / (1 + i * 0.25)
        matching = next(
            (
                e
                for e in edges
                if {e.source, e.target} == {src_node.entity_id, tgt_node.entity_id}
            ),
            None,
        )
        if matching is None:
            continue
        for ev in matching.evidence:
            if ev.pmid:
                pmid_weights[ev.pmid] = max(pmid_weights.get(ev.pmid, 0.0), weight)

    sorted_pairs = sorted(pmid_weights.items(), key=lambda x: x[1], reverse=True)
    return sorted_pairs[:_MAX_PMIDS]


def _fetch_s2_papers(
    pmid_weights: list[tuple[str, float]],
    api_key: str,
) -> list[dict]:
    """Fetch paper metadata from Semantic Scholar batch API.

    Falls back gracefully to an empty list on any failure.
    """
    if not pmid_weights:
        return []

    ids = [f"PMID:{pmid}" for pmid, _ in pmid_weights]
    body = json.dumps({"ids": ids}).encode("utf-8")
    url = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,abstract,tldr,year"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            papers: list[dict | None] = json.loads(resp.read().decode("utf-8"))
        return [p for p in papers if p is not None]
    except Exception as exc:
        logger.warning("Semantic Scholar API failed, using edge evidence only: %s", exc)
        return []


def _build_deep_think_prompt(
    path: list[DeepThinkPathNode],
    papers: list[dict],
    edges: list[DeepThinkEdge],
) -> str:
    # Build path chain with predicates
    chain_parts: list[str] = []
    for i, node in enumerate(path):
        label = f"{node.entity_name} ({node.entity_type})"
        if i > 0 and node.edge_predicate:
            chain_parts.append(f"--[{node.edge_predicate}]-->")
        chain_parts.append(label)
    path_chain = " ".join(chain_parts)

    # Fallback: build snippets from edge evidence if no S2 papers
    paper_lines: list[str] = []
    if papers:
        for p in papers:
            title = p.get("title") or "Untitled"
            year = p.get("year") or "n/a"
            abstract = p.get("abstract") or ""
            tldr_obj = p.get("tldr") or {}
            tldr = tldr_obj.get("text") or "" if isinstance(tldr_obj, dict) else ""
            paper_lines.append(
                f"Title: {title}\nYear: {year}\nAbstract: {abstract}\nTLDR: {tldr}"
            )
    else:
        # Use edge evidence snippets as fallback
        for edge in edges:
            for ev in edge.evidence[:3]:
                if ev.title or ev.snippet:
                    line = f"Title: {ev.title or 'n/a'}\nSnippet: {ev.snippet}"
                    paper_lines.append(line)

    papers_section = "\n\n---\n\n".join(paper_lines) if paper_lines else "No papers available."

    return f"""You are a biomedical knowledge graph explainer with deep expertise.

Path to analyze:
{path_chain}

Supporting papers (highest relevance first):
{papers_section}

Task:
Explain why these entities are connected along this path. For each link, describe the biological mechanism or association that connects them, citing specific papers by their titles. Keep the explanation focused and grounded in the provided evidence (150-300 words). If evidence is weak or absent for a link, say so explicitly. Do not invent facts.

End your response with: "Cited papers: [list titles]"
""".strip()


def _build_verification_prompt(analysis: str, papers: list[dict]) -> str:
    paper_titles = [p.get("title") or "Untitled" for p in papers]
    titles_list = "\n".join(f"- {t}" for t in paper_titles) if paper_titles else "- none"

    return f"""You are a rigorous scientific fact-checker.

The following analysis was generated about a biomedical knowledge graph path:

--- ANALYSIS ---
{analysis}
--- END ANALYSIS ---

Available source papers:
{titles_list}

Verify the analysis:
1. Does every factual claim map to one of the listed source papers?
2. Are any papers cited that are NOT in the source list above (hallucinated citations)?
3. Are there unsupported claims presented as fact?

Respond concisely with: VERIFIED (no issues found) or ISSUES FOUND: [list problems].
""".strip()


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _run_verification(analysis: str, papers: list[dict]) -> None:
    """Run background fact-check; result is logged only."""
    try:
        client = _get_genai_client()
        prompt = _build_verification_prompt(analysis, papers)
        response = client.models.generate_content(
            model=settings.GEMINI_DEEP_THINK_MODEL,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=prompt)],
                )
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=300,
            ),
        )
        result_text = getattr(response, "text", "") or ""
        if "ISSUES FOUND" in result_text.upper():
            logger.warning("Deep Think verification found issues: %s", result_text)
        else:
            logger.info("Deep Think verification: %s", result_text[:120])
    except Exception as exc:
        logger.warning("Deep Think verification call failed: %s", exc)


def stream_deep_think_events(request: DeepThinkRequest) -> Iterator[str]:
    path = request.path
    edges = request.edges

    # Summarize path for start event
    path_summary = " → ".join(n.entity_name for n in path)

    yield _sse(
        "start",
        {
            "path_summary": path_summary,
            "node_count": len(path),
        },
    )

    # Extract weighted PMIDs and fetch papers
    try:
        pmid_weights = _extract_weighted_pmids(path, edges)
        papers = _fetch_s2_papers(pmid_weights, settings.SEMANTIC_SCHOLAR_API_KEY)
    except Exception as exc:
        logger.exception("Deep Think: failed to prepare paper context")
        yield _sse("error", {"message": "Failed to retrieve supporting papers.", "detail": str(exc)})
        return

    # Send papers_loaded event
    paper_meta = [
        {
            "pmid": pmid_weights[i][0] if i < len(pmid_weights) else None,
            "title": p.get("title") or "Untitled",
            "year": p.get("year"),
            "abstract_snippet": (p.get("abstract") or "")[:300],
        }
        for i, p in enumerate(papers)
    ]

    # Add fallback entries from edge evidence if no S2 papers
    if not papers:
        for edge in edges:
            for ev in edge.evidence[:2]:
                if ev.pmid and ev.title:
                    paper_meta.append(
                        {"pmid": ev.pmid, "title": ev.title, "year": None, "abstract_snippet": ev.snippet[:300]}
                    )

    yield _sse("papers_loaded", {"papers": paper_meta, "count": len(paper_meta)})

    # Stream analysis from Gemini Pro
    full_text = ""
    try:
        client = _get_genai_client()
        prompt = _build_deep_think_prompt(path, papers, edges)

        stream = client.models.generate_content_stream(
            model=settings.GEMINI_DEEP_THINK_MODEL,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=prompt)],
                )
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=600,
            ),
        )

        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text is None:
                text = ""
                if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                    text = "".join(part.text or "" for part in chunk.candidates[0].content.parts)
            if not text:
                continue
            full_text += text
            yield _sse("delta", {"text": text})

    except Exception as exc:
        logger.exception("Deep Think: Gemini streaming failed")
        yield _sse(
            "error",
            {
                "message": "AI analysis generation failed.",
                "partial_text": full_text,
                "detail": str(exc),
            },
        )
        return

    # Fire-and-forget background verification
    threading.Thread(
        target=_run_verification,
        args=(full_text, papers),
        daemon=True,
    ).start()

    yield _sse("done", {"text": full_text})
