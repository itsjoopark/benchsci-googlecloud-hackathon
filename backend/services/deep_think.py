from __future__ import annotations

import json
import logging
import re
import threading
import urllib.error
import urllib.request
from typing import Iterator

from google.genai import types as genai_types

from backend.config import settings
from backend.models.deep_think import (
    DeepThinkChatMessage,
    DeepThinkChatRequest,
    DeepThinkEdge,
    DeepThinkPathNode,
    DeepThinkRequest,
)
from backend.services.overview import _get_genai_client

logger = logging.getLogger(__name__)

_MAX_PMIDS = 30


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

    return f"""You are an expert biomedical scientist analyzing a multi-hop knowledge graph path.

## Path
{path_chain}

## Supporting Literature
{papers_section}

## Your Task
Write a detailed scientific explanation of how these entities are connected along this path. Structure your response as follows:

1. **Overall connection**: One paragraph summarizing the high-level biological relationship across the entire path.
2. **Step-by-step mechanistic breakdown**: For each consecutive pair of entities in the path, dedicate a paragraph explaining the specific molecular mechanism, pathway interaction, or clinical association that links them. Reference specific findings from the provided papers (cite by title).
3. **Strength of evidence**: Briefly note where the evidence is strong vs. where it is circumstantial or inferred.

Rules:
- Ground every claim in the provided papers. Do not invent facts.
- If evidence for a specific link is absent, explicitly state that.
- Aim for 300-500 words total.
- End with: "Key references: [comma-separated list of cited paper titles]"
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


def _deep_think_model_candidates() -> list[str]:
    """Primary deep-think model, falling back to the overview model then flash."""
    seen: set[str] = set()
    candidates: list[str] = []
    for m in [
        settings.GEMINI_DEEP_THINK_MODEL.strip(),
        settings.GEMINI_OVERVIEW_MODEL.strip(),
        "gemini-2.5-flash",
        "gemini-2.0-flash-001",
    ]:
        if m and m not in seen:
            seen.add(m)
            candidates.append(m)
    return candidates


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _run_verification(analysis: str, papers: list[dict]) -> None:
    """Run background fact-check; result is logged only."""
    try:
        client = _get_genai_client()
        prompt = _build_verification_prompt(analysis, papers)
        verify_model = _deep_think_model_candidates()[0]
        response = client.models.generate_content(
            model=verify_model,
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

    # Stream analysis with model fallback
    full_text = ""
    try:
        client = _get_genai_client()
        prompt = _build_deep_think_prompt(path, papers, edges)
        config = genai_types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1500,
        )
        contents = [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=prompt)],
            )
        ]

        import itertools

        stream = None
        last_exc: Exception | None = None
        for model_name in _deep_think_model_candidates():
            try:
                candidate_stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                first_chunk = next(candidate_stream)
                stream = itertools.chain([first_chunk], candidate_stream)
                break
            except Exception as exc:
                last_exc = exc
                logger.warning("Deep Think model unavailable: %s (%s)", model_name, exc)

        if stream is None:
            raise last_exc or RuntimeError("No Deep Think model candidates available")

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
                "message": f"AI analysis generation failed: {type(exc).__name__}: {exc}",
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


# ── Chat feature ──────────────────────────────────────────────────────────────

_COMPRESSION_THRESHOLD = 100_000  # characters; Pro has 2M token context so compress only if very large


def _build_papers_context(papers: list[dict], edge_fallback: list[DeepThinkEdge]) -> str:
    """Format S2 papers (or edge evidence fallback) into a single context string."""
    if papers:
        sections = []
        for i, p in enumerate(papers):
            title = p.get("title") or "Untitled"
            year = p.get("year") or "n/a"
            abstract = p.get("abstract") or ""
            tldr_obj = p.get("tldr") or {}
            tldr = tldr_obj.get("text") or "" if isinstance(tldr_obj, dict) else ""
            sections.append(
                f"[{i + 1}] {title} ({year})\n"
                f"Abstract: {abstract}\n"
                f"{'Summary: ' + tldr if tldr else ''}"
            )
        return "\n\n".join(sections)

    # Fallback: edge evidence snippets
    lines: list[str] = []
    for edge in edge_fallback:
        for ev in edge.evidence[:3]:
            if ev.title or ev.snippet:
                lines.append(f"- {ev.title or 'n/a'}: {ev.snippet}")
    return "\n".join(lines) if lines else "No supporting literature available."


def _maybe_compress_context(
    papers_context: str,
    question: str,
    path: list[DeepThinkPathNode] | None = None,
) -> str:
    """If the paper context is large, use the Pro model to extract relevant passages.

    Uses the primary deep-think model (Pro) rather than Flash to preserve
    scientific nuance.  The user's question and path are included so the
    compression is query-aware.
    """
    if len(papers_context) <= _COMPRESSION_THRESHOLD:
        return papers_context

    path_chain = (
        " → ".join(f"{n.entity_name} ({n.entity_type})" for n in path)
        if path
        else "unknown path"
    )

    prompt = (
        f"A researcher is exploring this biomedical knowledge-graph path:\n"
        f"PATH: {path_chain}\n\n"
        f"Their specific question is:\n"
        f"QUESTION: {question}\n\n"
        "Below are supporting literature abstracts for the entities in this path. "
        "Your task: extract and summarize ONLY the findings that are directly relevant "
        "to answering the researcher's question about this path. "
        "Preserve paper numbers, titles, and the specific mechanistic details that bear "
        "on the question. Be concise (max 3 000 words). Omit papers with no relevance.\n\n"
        f"Papers:\n{papers_context[:80_000]}"
    )
    try:
        client = _get_genai_client()
        # Use the Pro model for compression to retain scientific precision
        compress_model = _deep_think_model_candidates()[0]
        resp = client.models.generate_content(
            model=compress_model,
            contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
            config=genai_types.GenerateContentConfig(temperature=0.1, max_output_tokens=4_000),
        )
        compressed = getattr(resp, "text", "") or ""
        logger.info("Context compressed via %s: %d→%d chars", compress_model, len(papers_context), len(compressed))
        return compressed if compressed else papers_context[:_COMPRESSION_THRESHOLD]
    except Exception as exc:
        logger.warning("Context compression failed, truncating: %s", exc)
        return papers_context[:_COMPRESSION_THRESHOLD]


def _review_response(question: str, papers_context: str, response: str) -> dict:
    """Reviewer LLM that returns a confidence score 1-10.

    Uses a tightly structured prompt and lenient multi-pattern regex so the
    score is reliably extracted even when the model adds preamble text or
    uses lowercase/alternate phrasing.
    """
    prompt = (
        "You are a scientific accuracy reviewer. Score the following AI response.\n\n"
        f"USER QUESTION: {question}\n\n"
        f"SUPPORTING PAPERS (excerpt):\n{papers_context[:8_000]}\n\n"
        f"AI RESPONSE:\n{response}\n\n"
        "Evaluate: (1) are all claims grounded in the provided papers? "
        "(2) is the science accurate? (3) is the answer complete?\n\n"
        "You MUST respond with only these two lines — nothing before, nothing after:\n"
        "CONFIDENCE: <integer 1-10>/10\n"
        "REASONING: <one sentence explaining the score>\n\n"
        "Example of a correct response:\n"
        "CONFIDENCE: 8/10\n"
        "REASONING: All key claims are directly supported by the cited abstracts."
    )
    try:
        client = _get_genai_client()
        # Use the same model chain as the main response for consistency
        review_model = _deep_think_model_candidates()[0]
        resp = client.models.generate_content(
            model=review_model,
            contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
            config=genai_types.GenerateContentConfig(temperature=0.0, max_output_tokens=300),
        )
        text = getattr(resp, "text", "") or ""
        logger.info("Reviewer raw response (%s): %s", review_model, text[:400])

        # Multi-pattern extraction — most specific first
        score_m = (
            re.search(r"CONFIDENCE:\s*(\d+)\s*/\s*10", text, re.IGNORECASE)
            or re.search(r"(\d+)\s*/\s*10", text)
            or re.search(r"score[:\s]+(\d+)", text, re.IGNORECASE)
        )
        reason_m = re.search(r"REASONING:\s*(.+)", text, re.DOTALL | re.IGNORECASE)

        score = int(score_m.group(1)) if score_m else 5
        reasoning = reason_m.group(1).strip()[:300] if reason_m else text.strip()[:300]
        return {"score": min(10, max(1, score)), "reasoning": reasoning}
    except Exception as exc:
        logger.warning("Reviewer LLM failed: %s", exc)
        return {"score": 0, "reasoning": ""}


def _build_system_instruction(path: list[DeepThinkPathNode], papers_context: str) -> str:
    path_chain = " → ".join(f"{n.entity_name} ({n.entity_type})" for n in path)
    return (
        "You are an expert biomedical scientist helping a researcher explore a knowledge graph.\n\n"
        f"The researcher has built this exploration path:\nPATH: {path_chain}\n\n"
        "Supporting literature for the entities in this path:\n"
        f"{papers_context}\n\n"
        "Guidelines:\n"
        "- Answer questions about these entities and their connections with scientific precision.\n"
        "- Ground every claim in the supporting literature; cite specific paper findings.\n"
        "- If the evidence is limited or absent, say so explicitly.\n"
        "- Be clear and concise (150-350 words per answer).\n"
        "- Do not invent facts beyond what the evidence supports.\n"
        "- Do not use markdown formatting symbols (no **, ##, etc.); write in plain prose."
    )


def stream_deep_think_chat_events(request: DeepThinkChatRequest) -> Iterator[str]:
    import itertools

    path = request.path
    edges = request.edges
    question = request.question
    history = request.messages

    path_summary = " → ".join(n.entity_name for n in path)
    yield _sse("start", {"path_summary": path_summary, "node_count": len(path)})

    # Step 1 — fetch papers
    try:
        pmid_weights = _extract_weighted_pmids(path, edges)
        papers = _fetch_s2_papers(pmid_weights, settings.SEMANTIC_SCHOLAR_API_KEY)
    except Exception as exc:
        logger.warning("Paper fetch failed, continuing without S2: %s", exc)
        papers = []
        pmid_weights = []

    paper_meta = [
        {
            "pmid": pmid_weights[i][0] if i < len(pmid_weights) else None,
            "title": p.get("title") or "Untitled",
            "year": p.get("year"),
            "abstract_snippet": (p.get("abstract") or "")[:250],
        }
        for i, p in enumerate(papers)
    ]
    # Edge-evidence fallback for metadata
    if not paper_meta:
        for edge in edges:
            for ev in edge.evidence[:2]:
                if ev.pmid and ev.title:
                    paper_meta.append(
                        {"pmid": ev.pmid, "title": ev.title, "year": None, "abstract_snippet": ev.snippet[:250]}
                    )

    yield _sse("papers_loaded", {"papers": paper_meta, "count": len(paper_meta)})

    # Step 2 — build + optionally compress paper context (Pro, query-aware)
    papers_context = _build_papers_context(papers, edges)
    papers_context = _maybe_compress_context(papers_context, question, path)

    # Step 3 — build system instruction and conversation contents
    system_instruction = _build_system_instruction(path, papers_context)

    contents: list[genai_types.Content] = []
    # Include last 10 turns to avoid token overflow
    for msg in history[-20:]:
        role = "user" if msg.role == "user" else "model"
        contents.append(
            genai_types.Content(role=role, parts=[genai_types.Part(text=msg.content)])
        )
    contents.append(
        genai_types.Content(role="user", parts=[genai_types.Part(text=question)])
    )

    # Step 4 — stream main response (Pro with fallbacks)
    full_text = ""
    try:
        client = _get_genai_client()
        config = genai_types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=4_000,
            system_instruction=system_instruction,
        )

        stream = None
        last_exc: Exception | None = None
        for model_name in _deep_think_model_candidates():
            try:
                candidate = client.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                first_chunk = next(candidate)
                stream = itertools.chain([first_chunk], candidate)
                logger.info("Deep Think chat using model: %s", model_name)
                break
            except Exception as exc:
                last_exc = exc
                logger.warning("Model %s unavailable for chat: %s", model_name, exc)

        if stream is None:
            raise last_exc or RuntimeError("No model candidates available")

        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text is None:
                text = ""
                try:
                    if chunk.candidates[0].content.parts:
                        text = "".join(p.text or "" for p in chunk.candidates[0].content.parts)
                except Exception:
                    pass
            if text:
                full_text += text
                yield _sse("delta", {"text": text})

    except Exception as exc:
        logger.exception("Deep Think chat: generation failed")
        yield _sse(
            "error",
            {
                "message": f"Generation failed: {type(exc).__name__}: {exc}",
                "partial_text": full_text,
            },
        )
        return

    # Step 5 — reviewer (synchronous Flash call, result shown to user)
    confidence: dict = {"score": 0, "reasoning": ""}
    try:
        confidence = _review_response(question, papers_context, full_text)
        logger.info(
            "Deep Think reviewer: %d/10 — %s",
            confidence["score"],
            confidence["reasoning"][:80],
        )
    except Exception as exc:
        logger.warning("Reviewer failed: %s", exc)

    # Step 6 — extract actually-cited papers from the response text
    cited_indices: set[int] = set()
    for m in re.finditer(r"\[(\d+(?:[,\s]*\d+)*)\]", full_text):
        for num_str in m.group(1).split(","):
            num_str = num_str.strip()
            if num_str.isdigit():
                idx = int(num_str) - 1  # 0-based
                if 0 <= idx < len(paper_meta):
                    cited_indices.add(idx)
    cited_papers = [{"index": i + 1, **paper_meta[i]} for i in sorted(cited_indices)]

    yield _sse("done", {"text": full_text, "confidence": confidence, "cited_papers": cited_papers})
