from backend.models.overview import (
    OverviewEdge,
    OverviewEntity,
    OverviewEvidence,
    OverviewHistoryItem,
    OverviewStreamRequest,
)
from backend.services import overview


def _base_entities() -> list[OverviewEntity]:
    return [
        OverviewEntity(id="NCBIGene:672", name="BRCA1", type="gene"),
        OverviewEntity(id="MESH:D001943", name="Breast Neoplasms", type="disease"),
        OverviewEntity(id="NCBIGene:675", name="BRCA2", type="gene"),
    ]


def test_selection_context_edge_passthrough():
    edge = OverviewEdge(
        id="e1",
        source="NCBIGene:672",
        target="MESH:D001943",
        predicate="biolink:related_to",
        label="related to",
        provenance="literature",
        sourceDb="kg_raw",
        evidence=[
            OverviewEvidence(
                id="ev-1",
                pmid="1234",
                title="test",
                snippet="test snippet",
                source="PubMed",
                sourceDb="PubMed",
            )
        ],
    )

    req = OverviewStreamRequest(
        selection_type="edge",
        edge_id="e1",
        center_node_id="NCBIGene:672",
        entities=_base_entities(),
        edges=[edge],
        history=[],
    )

    ctx = overview._build_selection_context(req)

    assert ctx.selection_key == "edge:e1"
    assert ctx.edge.id == "e1"
    assert ctx.source is not None and ctx.source.name == "BRCA1"


def test_selection_context_node_prefers_direct_center_edge():
    direct = OverviewEdge(
        id="direct",
        source="NCBIGene:672",
        target="MESH:D001943",
        predicate="biolink:related_to",
        label="related to",
        score=0.8,
        provenance="literature",
        sourceDb="kg_raw",
        evidence=[],
    )
    other = OverviewEdge(
        id="other",
        source="NCBIGene:675",
        target="MESH:D001943",
        predicate="biolink:related_to",
        label="related to",
        score=0.99,
        provenance="literature",
        sourceDb="kg_raw",
        evidence=[],
    )

    req = OverviewStreamRequest(
        selection_type="node",
        node_id="MESH:D001943",
        center_node_id="NCBIGene:672",
        entities=_base_entities(),
        edges=[other, direct],
        history=[],
    )

    ctx = overview._build_selection_context(req)
    assert ctx.selection_key == "node:MESH:D001943"
    assert ctx.edge.id == "direct"


def test_sse_stream_event_order(monkeypatch):
    edge = OverviewEdge(
        id="e1",
        source="NCBIGene:672",
        target="MESH:D001943",
        predicate="biolink:related_to",
        label="related to",
        provenance="literature",
        sourceDb="kg_raw",
        evidence=[],
    )
    req = OverviewStreamRequest(
        selection_type="edge",
        edge_id="e1",
        center_node_id="NCBIGene:672",
        entities=_base_entities(),
        edges=[edge],
        history=[OverviewHistoryItem(selection_key="edge:e0", selection_type="edge", summary="older")],
    )

    class _Chunk:
        def __init__(self, text: str):
            self.text = text

    def _mock_stream(*_args, **_kwargs):
        return iter([_Chunk("Hello "), _Chunk("world")]), "gemini-test-model"

    monkeypatch.setattr(overview, "_retrieve_rag_chunks", lambda _ctx: [])
    monkeypatch.setattr(overview, "_stream_overview_generation", _mock_stream)

    events = list(overview.stream_overview_events(req))

    assert events[0].startswith("event: start")
    assert events[1].startswith("event: context")
    assert any(e.startswith("event: delta") for e in events)
    assert events[-1].startswith("event: done")
