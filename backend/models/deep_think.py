from pydantic import BaseModel, Field


class DeepThinkPathNode(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: str
    edge_predicate: str | None = None


class DeepThinkEdgeEvidence(BaseModel):
    pmid: str | None = None
    title: str | None = None
    snippet: str = ""


class DeepThinkEdge(BaseModel):
    source: str
    target: str
    predicate: str
    evidence: list[DeepThinkEdgeEvidence] = Field(default_factory=list)


class DeepThinkRequest(BaseModel):
    path: list[DeepThinkPathNode]
    edges: list[DeepThinkEdge]
    question: str | None = None


class DeepThinkChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class DeepThinkChatRequest(BaseModel):
    path: list[DeepThinkPathNode]
    edges: list[DeepThinkEdge]
    question: str
    messages: list[DeepThinkChatMessage] = Field(default_factory=list)
