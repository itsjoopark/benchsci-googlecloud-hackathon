import type { Entity, GraphEdge, EvidenceItem, EntityType } from "../types";
import type { JsonNode, JsonEdge, JsonEvidence, JsonGraphPayload } from "../types/api";

export function biolinkTypeToEntityType(type: string): EntityType {
  const map: Record<string, EntityType> = {
    "biolink:Gene": "gene",
    "biolink:DiseaseOrPhenotypicFeature": "disease",
    "biolink:Drug": "drug",
    "biolink:Pathway": "pathway",
    "biolink:Protein": "protein",
  };
  return map[type] ?? "gene";
}

export function jsonNodeToEntity(node: JsonNode): Entity {
  const entityType = biolinkTypeToEntityType(node.type);
  const metadata: Record<string, string | number | string[] | undefined> = {};
  for (const [k, v] of Object.entries(node.metadata)) {
    if (v !== undefined && v !== null) {
      metadata[k] = v as string | number | string[];
    }
  }
  return {
    id: node.id,
    name: node.name,
    type: entityType,
    primaryId: node.id,
    metadata,
    color: node.color,
    size: node.size,
    layoutX: node.x,
    layoutY: node.y,
  };
}

export function jsonEvidenceToEvidenceItem(ev: JsonEvidence, index: number): EvidenceItem {
  return {
    id: `ev-${index}`,
    pmid: ev.pmid,
    year: ev.pub_year,
    snippet: ev.snippet,
    source: ev.source,
    sourceDb: ev.source,
  };
}

export function jsonEdgeToGraphEdge(edge: JsonEdge): GraphEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    predicate: edge.predicate,
    label: edge.label,
    score: edge.confidence_score,
    provenance: edge.provenance === "curated_db" ? "curated" : "literature",
    sourceDb: edge.source_db,
    evidence: edge.evidence.map((ev, i) => jsonEvidenceToEvidenceItem(ev, i)),
    color: edge.color,
    paperCount: edge.paper_count,
    trialCount: edge.trial_count,
    patentCount: edge.patent_count,
    cooccurrenceScore: edge.cooccurrence_score,
  };
}

export function jsonPayloadToGraph(payload: JsonGraphPayload): {
  entities: Entity[];
  edges: GraphEdge[];
} {
  const entities = payload.nodes.map(jsonNodeToEntity);
  const edges = payload.edges.map(jsonEdgeToGraphEdge);
  return { entities, edges };
}
