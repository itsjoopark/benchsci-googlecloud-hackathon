from pydantic import BaseModel, Field


class OverviewEntity(BaseModel):
    id: str
    name: str
    type: str


class OverviewEvidence(BaseModel):
    id: str | None = None
    pmid: str | None = None
    title: str | None = None
    year: int | None = None
    snippet: str
    source: str | None = None
    sourceDb: str | None = None


class OverviewEdge(BaseModel):
    id: str
    source: str
    target: str
    predicate: str
    label: str | None = None
    score: float | None = None
    provenance: str
    sourceDb: str
    evidence: list[OverviewEvidence] = Field(default_factory=list)
    paper_count: int | None = None
    trial_count: int | None = None
    patent_count: int | None = None
    cooccurrence_score: int | None = None


class OverviewHistoryItem(BaseModel):
    selection_key: str
    selection_type: str
    summary: str


class OverviewPathEntity(BaseModel):
    id: str
    name: str
    type: str


class OverviewStreamRequest(BaseModel):
    selection_type: str = Field(..., pattern=r"^(edge|node)$")
    edge_id: str | None = None
    node_id: str | None = None
    center_node_id: str = Field(..., min_length=1)
    entities: list[OverviewEntity] = Field(default_factory=list)
    edges: list[OverviewEdge] = Field(default_factory=list)
    history: list[OverviewHistoryItem] = Field(default_factory=list)
    path: list[OverviewPathEntity] = Field(default_factory=list)
