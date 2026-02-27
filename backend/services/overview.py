from __future__ import annotations

import json
import itertools
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

import vertexai
from google import genai
from google.genai import types as genai_types
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import aiplatform, bigquery
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from backend.config import settings
from backend.services.orkg_context import get_orkg_context
from backend.models.overview import (
    OverviewEdge,
    OverviewEntity,
    OverviewHistoryItem,
    OverviewPathEntity,
    OverviewStreamRequest,
)

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    id: str
    kind: str
    label: str


@dataclass
class RagChunk:
    chunk_id: str
    doc_id: str
    doc_type: str
    chunk_text: str
    source_id: str
    distance: float


@dataclass
class SelectionContext:
    selection_key: str
    selection_type: str
    edge: OverviewEdge
    source: OverviewEntity | None
    target: OverviewEntity | None
    related_edges: list[OverviewEdge]
    center_overview: bool
    entity_lookup: dict[str, OverviewEntity]


_bq_client: bigquery.Client | None = None
_embed_model: TextEmbeddingModel | None = None
_genai_client: genai.Client | None = None
_resolved_generation_model_name: str | None = None
_index_endpoint: aiplatform.MatchingEngineIndexEndpoint | None = None


def _get_bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=settings.GCP_PROJECT_ID)
    return _bq_client


def _get_embed_model() -> TextEmbeddingModel:
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    vertexai.init(project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
    try:
        _embed_model = TextEmbeddingModel.from_pretrained(settings.OVERVIEW_EMBEDDING_MODEL)
    except Exception:
        _embed_model = TextEmbeddingModel.from_pretrained(settings.OVERVIEW_EMBEDDING_MODEL_FALLBACK)
    return _embed_model


def _get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=settings.GEMINI_OVERVIEW_LOCATION,
        )
    return _genai_client


def _stream_overview_generation(prompt: str) -> tuple[Iterator[genai_types.GenerateContentResponse], str]:
    client = _get_genai_client()
    config = genai_types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.9,
        max_output_tokens=600,
        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
    )
    model_name = settings.GEMINI_OVERVIEW_MODEL.strip()
    if not model_name:
        raise RuntimeError("GEMINI_OVERVIEW_MODEL is not configured")

    stream = client.models.generate_content_stream(
        model=model_name,
        contents=[
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=prompt)],
            )
        ],
        config=config,
    )
    first_chunk = next(stream)
    return itertools.chain([first_chunk], stream), model_name


def _get_index_endpoint() -> aiplatform.MatchingEngineIndexEndpoint:
    global _index_endpoint
    if _index_endpoint is None:
        aiplatform.init(project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
        _index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
            index_endpoint_name=settings.VERTEX_VECTOR_ENDPOINT_RESOURCE
        )
    return _index_endpoint


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))


def _pick_best_edge(candidates: Iterable[OverviewEdge]) -> OverviewEdge | None:
    ranked = sorted(candidates, key=lambda e: (e.score or 0.0, len(e.evidence or [])), reverse=True)
    return ranked[0] if ranked else None


def _build_selection_context(request: OverviewStreamRequest) -> SelectionContext:
    entities = {e.id: e for e in request.entities}

    if request.selection_type == "edge":
        edge = next((e for e in request.edges if e.id == request.edge_id), None)
        if edge is None:
            raise ValueError("Selected edge was not found in the provided graph payload")
        source = entities.get(edge.source)
        target = entities.get(edge.target)
        return SelectionContext(
            selection_key=f"edge:{edge.id}",
            selection_type="edge",
            edge=edge,
            source=source,
            target=target,
            related_edges=[edge],
            center_overview=False,
            entity_lookup=entities,
        )

    if not request.node_id:
        raise ValueError("node_id is required when selection_type=node")

    center_id = request.center_node_id
    node_id = request.node_id

    if node_id == center_id:
        center_edges = [
            e for e in request.edges if e.source == center_id or e.target == center_id
        ]
        ranked_center_edges = sorted(
            center_edges,
            key=lambda e: (e.score or 0.0, len(e.evidence or [])),
            reverse=True,
        )
        related_edges = ranked_center_edges[:10]
        if not related_edges:
            raise ValueError("Center node has no visible connected edges")

        seen_evidence_keys: set[str] = set()
        merged_evidence = []
        for edge_item in related_edges:
            for ev in edge_item.evidence:
                ev_key = ev.id or ev.pmid or f"{ev.title or ''}|{ev.snippet[:120]}"
                if ev_key in seen_evidence_keys:
                    continue
                seen_evidence_keys.add(ev_key)
                merged_evidence.append(ev)
                if len(merged_evidence) >= 24:
                    break
            if len(merged_evidence) >= 24:
                break

        aggregate_edge = OverviewEdge(
            id=f"center:{center_id}:all-visible",
            source=center_id,
            target="__all_visible_neighbors__",
            predicate="center_node_overview",
            label="center node relation to visible nodes",
            score=related_edges[0].score,
            provenance=related_edges[0].provenance,
            sourceDb=related_edges[0].sourceDb,
            evidence=merged_evidence,
            paper_count=sum((e.paper_count or 0) for e in related_edges),
            trial_count=sum((e.trial_count or 0) for e in related_edges),
            patent_count=sum((e.patent_count or 0) for e in related_edges),
            cooccurrence_score=related_edges[0].cooccurrence_score,
        )

        return SelectionContext(
            selection_key=f"node:{node_id}",
            selection_type="node",
            edge=aggregate_edge,
            source=entities.get(center_id),
            target=None,
            related_edges=related_edges,
            center_overview=True,
            entity_lookup=entities,
        )

    direct_edges = [
        e
        for e in request.edges
        if {e.source, e.target} == {center_id, node_id}
    ]
    chosen = _pick_best_edge(direct_edges)

    if chosen is None:
        center_neighbors = {
            e.target if e.source == center_id else e.source
            for e in request.edges
            if e.source == center_id or e.target == center_id
        }
        bridge_edges = [
            e
            for e in request.edges
            if (e.source == node_id and e.target in center_neighbors)
            or (e.target == node_id and e.source in center_neighbors)
        ]
        chosen = _pick_best_edge(bridge_edges)

    if chosen is None:
        node_edges = [e for e in request.edges if e.source == node_id or e.target == node_id]
        chosen = _pick_best_edge(node_edges)

    if chosen is None:
        # Fallback: generate overview from node metadata alone (no edge required)
        node_entity = entities.get(node_id)
        fallback_edge = OverviewEdge(
            id=f"fallback:{node_id}",
            source=node_id,
            target=center_id,
            predicate="related_to",
            label="related to",
            score=None,
            provenance="",
            sourceDb="",
            evidence=[],
            paper_count=None,
            trial_count=None,
            patent_count=None,
            cooccurrence_score=None,
        )
        return SelectionContext(
            selection_key=f"node:{node_id}",
            selection_type="node",
            edge=fallback_edge,
            source=node_entity,
            target=entities.get(center_id),
            related_edges=[],
            center_overview=False,
            entity_lookup=entities,
        )

    source = entities.get(chosen.source)
    target = entities.get(chosen.target)

    return SelectionContext(
        selection_key=f"node:{node_id}",
        selection_type="node",
        edge=chosen,
        source=source,
        target=target,
        related_edges=[chosen],
        center_overview=False,
        entity_lookup=entities,
    )


def _normalize_citations(edge: OverviewEdge, rag_chunks: list[RagChunk], orkg_text: str = "") -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()

    for item in edge.evidence:
        if item.pmid:
            key = f"PMID:{item.pmid}"
            if key in seen:
                continue
            seen.add(key)
            citations.append(Citation(id=key, kind="evidence", label=key))

    for chunk in rag_chunks:
        source = chunk.source_id or chunk.doc_id
        key = source if ":" in source else f"DOC:{source}"
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(id=key, kind="rag", label=key))

    if orkg_text:
        for doi_match in re.finditer(r"DOI:\s*(10\.\S+)", orkg_text):
            doi = doi_match.group(1).rstrip("|").strip()
            key = f"DOI:{doi}"
            if key in seen:
                continue
            seen.add(key)
            citations.append(Citation(id=key, kind="orkg", label=key))

    return citations


def _build_query_text(context: SelectionContext) -> str:
    edge = context.edge
    source_name = context.source.name if context.source else edge.source
    target_name = context.target.name if context.target else edge.target
    rel = edge.label or edge.predicate

    evidence_source = edge.evidence
    if context.center_overview:
        evidence_source = [
            ev
            for rel_edge in context.related_edges[:6]
            for ev in rel_edge.evidence[:2]
        ]

    evidence_titles = [
        e.title.strip() for e in evidence_source if e.title and e.title.strip()
    ]
    evidence_snippets = [
        e.snippet.strip() for e in evidence_source if e.snippet and e.snippet.strip()
    ]
    evidence_bits = evidence_titles[:4] + evidence_snippets[:4]

    relation_bits: list[str] = []
    if context.center_overview and context.source:
        center_id = context.source.id
        for rel_edge in context.related_edges[:8]:
            other_id = rel_edge.target if rel_edge.source == center_id else rel_edge.source
            other_name = context.entity_lookup.get(other_id).name if other_id in context.entity_lookup else other_id
            relation_bits.append(f"{context.source.name} -> {other_name}: {rel_edge.label or rel_edge.predicate}")

    return "\n".join([
        f"source: {source_name}",
        f"target: {target_name}",
        f"predicate: {rel}",
        "relations:",
        *(relation_bits or ["none"]),
        "evidence:",
        *evidence_bits,
    ])


def _retrieve_rag_chunks(context: SelectionContext) -> list[RagChunk]:
    if not settings.VERTEX_VECTOR_ENDPOINT_RESOURCE or not settings.VERTEX_VECTOR_DEPLOYED_INDEX_ID:
        return []

    query_text = _build_query_text(context)

    try:
        embed_model = _get_embed_model()
        query_embedding = embed_model.get_embeddings(
            [TextEmbeddingInput(text=query_text, task_type="RETRIEVAL_QUERY")]
        )[0].values

        endpoint = _get_index_endpoint()
        result = endpoint.find_neighbors(
            deployed_index_id=settings.VERTEX_VECTOR_DEPLOYED_INDEX_ID,
            queries=[query_embedding],
            num_neighbors=settings.OVERVIEW_RAG_FETCH_K,
        )
    except Exception as exc:
        logger.warning("RAG retrieval unavailable, falling back to edge evidence only: %s", exc)
        return []

    if not result or not result[0]:
        return []

    neighbor_map: dict[str, float] = {}
    for n in result[0]:
        chunk_id = getattr(n, "id", None)
        if not chunk_id:
            continue
        dist = getattr(n, "distance", 0.0) or 0.0
        neighbor_map[chunk_id] = float(dist)

    if not neighbor_map:
        return []

    client = _get_bq_client()
    sql = f"""
    SELECT chunk_id, doc_id, doc_type, chunk_text, source_id
    FROM `{settings.GCP_PROJECT_ID}.{settings.OVERVIEW_RAG_DATASET}.{settings.OVERVIEW_RAG_EMBED_TABLE}`
    WHERE chunk_id IN UNNEST(@chunk_ids)
    """
    rows = list(
        client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("chunk_ids", "STRING", list(neighbor_map.keys())),
                ]
            ),
        ).result()
    )

    chunks = [
        RagChunk(
            chunk_id=str(r["chunk_id"]),
            doc_id=str(r["doc_id"]),
            doc_type=str(r["doc_type"]),
            chunk_text=str(r["chunk_text"]),
            source_id=str(r["source_id"]),
            distance=neighbor_map.get(str(r["chunk_id"]), 0.0),
        )
        for r in rows
    ]

    source_id = context.edge.source
    target_id = context.edge.target
    sql_filter = f"""
    SELECT doc_id
    FROM `{settings.GCP_PROJECT_ID}.{settings.OVERVIEW_RAG_DATASET}.{settings.OVERVIEW_RAG_ENTITY_TABLE}`
    WHERE entity_id IN (@source_id, @target_id)
      AND doc_id IN UNNEST(@doc_ids)
    GROUP BY doc_id
    HAVING COUNT(DISTINCT entity_id) = 2
    """
    doc_ids = list({c.doc_id for c in chunks})
    if not doc_ids:
        return []

    eligible_doc_ids: set[str] = set()
    if not context.center_overview:
        try:
            filter_rows = list(
                client.query(
                    sql_filter,
                    job_config=bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("source_id", "STRING", source_id),
                            bigquery.ScalarQueryParameter("target_id", "STRING", target_id),
                            bigquery.ArrayQueryParameter("doc_ids", "STRING", doc_ids),
                        ]
                    ),
                ).result()
            )
            eligible_doc_ids = {str(r["doc_id"]) for r in filter_rows}
        except GoogleAPICallError:
            eligible_doc_ids = set()

    if eligible_doc_ids:
        chunks = [c for c in chunks if c.doc_id in eligible_doc_ids]

    query_tokens = _tokenize(_build_query_text(context))

    def rank(chunk: RagChunk) -> float:
        sim = 1.0 / (1.0 + max(chunk.distance, 0.0))
        overlap = len(_tokenize(chunk.chunk_text) & query_tokens) / max(1, len(query_tokens))
        return (0.75 * sim) + (0.25 * overlap)

    chunks.sort(key=rank, reverse=True)
    return chunks[: settings.OVERVIEW_RAG_TOP_K]


def _prompt_text(context: SelectionContext, rag_chunks: list[RagChunk], history: list[OverviewHistoryItem], orkg_text: str = "", path: list[OverviewPathEntity] | None = None) -> str:
    edge = context.edge
    source_name = context.source.name if context.source else edge.source
    target_name = context.target.name if context.target else edge.target
    relationship = edge.label or edge.predicate

    evidence_lines: list[str] = []
    for item in edge.evidence[:8]:
        pmid = f"PMID:{item.pmid}" if item.pmid else "PMID:unknown"
        title = item.title or item.snippet
        year = str(item.year) if item.year else "n/a"
        evidence_lines.append(f"- {pmid} ({year}): {title}")

    rag_lines = [f"- {c.source_id or c.doc_id}: {c.chunk_text[:320]}" for c in rag_chunks[:8]]

    history_lines = [
        f"- {h.selection_key}: {h.summary[:240]}" for h in history[-settings.OVERVIEW_HISTORY_LIMIT :]
    ]

    if path:
        path_str = " → ".join(f"{p.name} ({p.type})" for p in path)
        path_line = f"Exploration path: {path_str}"
    else:
        path_line = ""

    relation_lines: list[str] = []
    if context.center_overview and context.source:
        center_id = context.source.id
        for rel_edge in context.related_edges[:10]:
            other_id = rel_edge.target if rel_edge.source == center_id else rel_edge.source
            other_name = context.entity_lookup.get(other_id).name if other_id in context.entity_lookup else other_id
            relation_lines.append(
                f"- {source_name} -> {other_name}: {rel_edge.label or rel_edge.predicate} (score={rel_edge.score or 0:.2f})"
            )

    if path and len(path) >= 2:
        path_names = " → ".join(p.name for p in path)
        selection_instruction = (
            f"Explain the full multi-hop exploration path: {path_names}. "
            "Describe how each entity connects to the next, what the overall biological or clinical significance of this chain is, "
            "and what insight can be drawn by traversing this entire sequence."
        )
    elif context.center_overview:
        selection_instruction = "Explain how the center node is related to all currently visible connected nodes, summarizing the strongest links."
    else:
        selection_instruction = "Explain why this specific selected connection exists."

    return f"""
You are a biomedical knowledge graph explainer.

Task: {selection_instruction}
Hard rules:
1) Do not invent facts.
2) Every claim must map to cited IDs from provided evidence or RAG context.
3) If evidence is weak or missing, say that explicitly.
4) Keep response concise (120-220 words).

Selected connection:
- source: {source_name} ({edge.source})
- target: {target_name} ({edge.target})
- predicate: {relationship}
- selection_type: {context.selection_type}
- center_overview: {str(context.center_overview).lower()}
- cooccurrence: papers={edge.paper_count or 0}, trials={edge.trial_count or 0}, patents={edge.patent_count or 0}

Visible center-node relations:
{chr(10).join(relation_lines) if relation_lines else '- n/a (not center selection)'}

Primary evidence:
{chr(10).join(evidence_lines) if evidence_lines else '- none'}

RAG supporting context:
{chr(10).join(rag_lines) if rag_lines else '- none'}

ORKG scholarly contributions:
{orkg_text if orkg_text else '- none'}

Exploration path (how the user arrived here):
{path_line if path_line else "- direct query (no prior exploration)"}

Previous session summaries:
{chr(10).join(history_lines) if history_lines else '- none'}

Output format:
- A short paragraph describing mechanism/association.
- End with "Citations:" followed by bracketed IDs, e.g. [PMID:123], [NCT:...].
""".strip()


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_overview_events(request: OverviewStreamRequest):
    try:
        context = _build_selection_context(request)
        rag_chunks = _retrieve_rag_chunks(context)

        orkg_text = ""
        if settings.ORKG_ENABLED and context.selection_type == "edge":
            try:
                orkg_text = get_orkg_context(
                    entity_a_id=context.edge.source,
                    entity_b_id=context.edge.target,
                    entity_a_type=context.source.type if context.source else None,
                    entity_b_type=context.target.type if context.target else None,
                )
            except Exception:
                logger.warning("ORKG context retrieval failed, continuing without", exc_info=True)

        citations = _normalize_citations(context.edge, rag_chunks, orkg_text)
    except Exception as exc:
        logger.exception("Failed to prepare overview context")
        yield _sse(
            "error",
            {
                "message": "Unable to build AI overview for the selected graph element.",
                "partial_text": "",
                "detail": str(exc),
            },
        )
        return

    yield _sse(
        "start",
        {
            "selection_key": context.selection_key,
            "selection_type": context.selection_type,
            "edge_id": context.edge.id,
            "source": context.edge.source,
            "target": context.edge.target,
        },
    )

    yield _sse(
        "context",
        {
            "citations": [c.__dict__ for c in citations],
            "rag_chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "source_id": c.source_id,
                    "doc_type": c.doc_type,
                }
                for c in rag_chunks
            ],
            "orkg_available": bool(orkg_text),
        },
    )

    full_text = ""

    def extract_chunk_text(chunk: genai_types.GenerateContentResponse) -> str:
        text = getattr(chunk, "text", None)
        if text:
            return text
        if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
            return "".join(part.text or "" for part in chunk.candidates[0].content.parts)
        return ""

    def compute_delta(current: str, previous_full: str) -> tuple[str, str]:
        # SDK responses can be either cumulative or delta-chunks.
        # Normalize to emitted deltas while preserving full text for done event.
        if not current:
            return "", previous_full
        if current.startswith(previous_full):
            return current[len(previous_full):], current
        if previous_full.startswith(current):
            return "", previous_full
        # Fallback for true delta chunks or mixed chunking behavior.
        return current, previous_full + current

    try:
        prompt = _prompt_text(context, rag_chunks, request.history, orkg_text, request.path or None)
        stream, chosen_model = _stream_overview_generation(prompt)
        global _resolved_generation_model_name
        _resolved_generation_model_name = chosen_model

        for chunk in stream:
            chunk_text = extract_chunk_text(chunk)
            delta, full_text = compute_delta(chunk_text, full_text)
            if not delta:
                continue
            yield _sse("delta", {"text": delta})

        yield _sse(
            "done",
            {
                "text": full_text,
                "citations": [c.__dict__ for c in citations],
                "selection_key": context.selection_key,
                "selection_type": context.selection_type,
                "model": _resolved_generation_model_name or settings.GEMINI_OVERVIEW_MODEL,
            },
        )
    except Exception as exc:
        logger.exception("Overview generation failed")
        yield _sse(
            "error",
            {
                "message": "AI overview generation failed. Showing available grounded context only.",
                "partial_text": full_text,
                "detail": str(exc),
            },
        )


def verify_vector_overview() -> dict:
    if not settings.VERTEX_VECTOR_ENDPOINT_RESOURCE or not settings.VERTEX_VECTOR_DEPLOYED_INDEX_ID:
        return {
            "ok": False,
            "reason": "Missing vector endpoint configuration",
        }

    try:
        embed_model = _get_embed_model()
        emb = embed_model.get_embeddings(
            [TextEmbeddingInput(text="BRCA1 breast cancer pathway", task_type="RETRIEVAL_QUERY")]
        )[0].values
        endpoint = _get_index_endpoint()
        neighbors = endpoint.find_neighbors(
            deployed_index_id=settings.VERTEX_VECTOR_DEPLOYED_INDEX_ID,
            queries=[emb],
            num_neighbors=5,
        )
        sample_ids = [getattr(n, "id", "") for n in (neighbors[0] if neighbors else [])]
        return {
            "ok": True,
            "neighbors_found": len(sample_ids),
            "sample_ids": sample_ids,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": str(exc),
        }
