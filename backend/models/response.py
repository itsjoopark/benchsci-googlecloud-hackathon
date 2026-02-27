from pydantic import BaseModel


class JsonEvidence(BaseModel):
    pmid: str
    snippet: str
    pub_year: int
    source: str


class JsonNode(BaseModel):
    id: str
    name: str
    type: str
    color: str | None = None
    size: float | None = None
    is_expanded: bool | None = None
    metadata: dict[str, object]


class JsonEdge(BaseModel):
    id: str
    source: str
    target: str
    predicate: str
    label: str
    color: str | None = None
    source_db: str
    direction: str
    confidence_score: float | None = None
    provenance: str
    evidence: list[JsonEvidence]
    paper_count: int = 0
    trial_count: int = 0
    patent_count: int = 0
    cooccurrence_score: int = 0


class JsonGraphPayload(BaseModel):
    center_node_id: str
    nodes: list[JsonNode]
    edges: list[JsonEdge]
    message: str | None = None
