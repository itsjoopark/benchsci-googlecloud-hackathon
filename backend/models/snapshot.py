from pydantic import BaseModel


class GraphSnapshotPayload(BaseModel):
    query: str
    entities: list[dict]
    edges: list[dict]
    expanded_nodes: list[str]
    center_node_id: str
    path_node_ids: list[str] = []
    entity_filter: str | list[str] = "all"
    node_positions: dict[str, dict] = {}
    selection_history: list[dict] = []
    selected_entity_id: str | None = None


class SnapshotResponse(BaseModel):
    id: str
