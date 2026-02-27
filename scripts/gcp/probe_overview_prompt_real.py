#!/usr/bin/env python3
"""Probe real overview RAG -> prompt wiring without fake chunk retrieval.

This script:
1) Builds a real OverviewStreamRequest.
2) Leaves _retrieve_rag_chunks untouched (real runtime path).
3) Temporarily wraps _stream_overview_generation to capture the exact prompt.
4) Runs stream_overview_events and prints whether RAG context lines were present.
"""

from __future__ import annotations

import json
import re
from typing import Iterator

from backend.models.overview import (
    OverviewEdge,
    OverviewEntity,
    OverviewEvidence,
    OverviewStreamRequest,
)
from backend.services import overview


class _DummyChunk:
    def __init__(self, text: str):
        self.text = text


def _build_request() -> OverviewStreamRequest:
    edge = OverviewEdge(
        id="NCBIGene:672--MESH:D001943--disease_associated_with_gene",
        source="NCBIGene:672",
        target="MESH:D001943",
        predicate="biolink:related_to",
        label="related to",
        score=0.87,
        provenance="literature",
        sourceDb="kg_raw",
        paper_count=12,
        evidence=[
            OverviewEvidence(
                id="ev-0",
                pmid="12345678",
                title="BRCA1 and breast cancer risk",
                year=2018,
                snippet="BRCA1 variants are associated with hereditary breast cancer.",
                source="PubMed",
                sourceDb="PubMed",
            )
        ],
    )

    return OverviewStreamRequest(
        selection_type="edge",
        edge_id=edge.id,
        center_node_id="NCBIGene:672",
        entities=[
            OverviewEntity(id="NCBIGene:672", name="BRCA1", type="gene"),
            OverviewEntity(id="MESH:D001943", name="Breast Neoplasms", type="disease"),
        ],
        edges=[edge],
        history=[],
    )


def main() -> None:
    request = _build_request()

    captured_prompt: dict[str, str] = {"text": ""}

    orig_stream = overview._stream_overview_generation

    def _capture_stream(prompt: str) -> tuple[Iterator[_DummyChunk], str]:
        captured_prompt["text"] = prompt
        return iter([_DummyChunk("probe")]), "probe-model"

    try:
        overview._stream_overview_generation = _capture_stream
        events = list(overview.stream_overview_events(request))
    finally:
        overview._stream_overview_generation = orig_stream

    context_event = next((e for e in events if e.startswith("event: context")), "")
    rag_chunk_count = 0
    if context_event:
        data_line = next((ln for ln in context_event.splitlines() if ln.startswith("data: ")), "")
        if data_line:
            payload = json.loads(data_line[6:])
            rag_chunk_count = len(payload.get("rag_chunks", []))

    prompt = captured_prompt["text"]
    rag_section_match = re.search(r"RAG supporting context:\n(.*?)\n\nORKG scholarly contributions:", prompt, re.S)
    rag_section = rag_section_match.group(1).strip() if rag_section_match else ""
    rag_in_prompt = bool(rag_section and rag_section != "- none")

    print(
        json.dumps(
            {
                "rag_chunks_in_context_event": rag_chunk_count,
                "rag_section_in_prompt": rag_in_prompt,
                "rag_section_preview": rag_section.splitlines()[:6],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
