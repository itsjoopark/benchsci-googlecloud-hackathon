from backend.mappings import (
    ENTITY_TYPE_TO_BIOLINK,
    BIOLINK_FALLBACK,
    RELATION_TYPE_TO_PREDICATE,
    PREDICATE_FALLBACK,
    ENTITY_TYPE_COLORS,
    COLOR_FALLBACK,
)
from backend.models.response import JsonEvidence, JsonNode, JsonEdge, JsonGraphPayload


def _biolink_type(raw_type: str | None) -> str:
    if not raw_type:
        return BIOLINK_FALLBACK
    return ENTITY_TYPE_TO_BIOLINK.get(raw_type.lower(), BIOLINK_FALLBACK)


def _entity_color(raw_type: str | None) -> str:
    if not raw_type:
        return COLOR_FALLBACK
    return ENTITY_TYPE_COLORS.get(raw_type.lower(), COLOR_FALLBACK)


def _predicate(relation_type: str | None) -> str:
    if not relation_type:
        return PREDICATE_FALLBACK
    return RELATION_TYPE_TO_PREDICATE.get(relation_type.lower(), PREDICATE_FALLBACK)


def _label_from_predicate(predicate: str) -> str:
    """Derive a human-readable label from a biolink predicate."""
    label = predicate.replace("biolink:", "").replace("_", " ")
    return label


def build_graph_payload(
    center_entity: dict,
    related_entities: list[dict],
    paper_details: dict[str, dict],
) -> JsonGraphPayload:
    center_id = center_entity["entity_id"]
    center_type = center_entity["type"]

    # Center node
    center_node = JsonNode(
        id=center_id,
        name=center_entity["mention"],
        type=_biolink_type(center_type),
        color=_entity_color(center_type),
        size=1.5,
        is_expanded=True,
        metadata={"entity_id": center_id},
    )

    nodes: dict[str, JsonNode] = {center_id: center_node}
    edges: list[JsonEdge] = []

    for rel in related_entities:
        other_id = rel["other_entity_id"]
        other_type = rel["other_type"]
        other_mention = rel["other_mention"] or other_id

        # Deduplicate nodes
        if other_id not in nodes:
            nodes[other_id] = JsonNode(
                id=other_id,
                name=other_mention,
                type=_biolink_type(other_type),
                color=_entity_color(other_type),
                size=1.0,
                is_expanded=False,
                metadata={"entity_id": other_id},
            )

        # Build evidence list
        evidence_items: list[JsonEvidence] = []
        for pmid in rel.get("pmids", []):
            paper = paper_details.get(pmid, {})
            evidence_items.append(
                JsonEvidence(
                    pmid=pmid,
                    snippet=paper.get("title", ""),
                    pub_year=paper.get("year", 0),
                    source="PubMed",
                )
            )

        predicate = _predicate(rel["relation_type"])
        direction = rel.get("direction", "->")

        # Edge source/target based on direction
        if direction == "->":
            source, target = center_id, other_id
        else:
            source, target = other_id, center_id

        edge_id = f"{source}--{target}--{rel['relation_type']}"
        edges.append(
            JsonEdge(
                id=edge_id,
                source=source,
                target=target,
                predicate=predicate,
                label=_label_from_predicate(predicate),
                color=_entity_color(other_type),
                source_db="kg_raw",
                direction=direction,
                confidence_score=min(rel.get("evidence_count", 1) / 10.0, 1.0),
                provenance="literature",
                evidence=evidence_items,
            )
        )

    return JsonGraphPayload(
        center_node_id=center_id,
        nodes=list(nodes.values()),
        edges=edges,
    )


def build_not_found_response(query: str) -> JsonGraphPayload:
    return JsonGraphPayload(
        center_node_id="",
        nodes=[],
        edges=[],
        message=f"No entity found matching '{query}'",
    )
