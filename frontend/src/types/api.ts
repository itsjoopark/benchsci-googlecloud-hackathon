export interface JsonNode {
  id: string;
  name: string;
  type: string;
  color?: string;
  size?: number;
  is_expanded?: boolean;
  metadata: Record<string, unknown>;
}

export interface JsonEvidence {
  pmid: string;
  snippet: string;
  pub_year: number;
  source: string;
}

export interface JsonEdge {
  id: string;
  source: string;
  target: string;
  predicate: string;
  label: string;
  color?: string;
  source_db: string;
  direction: string;
  confidence_score?: number;
  provenance: string;
  evidence: JsonEvidence[];
  paper_count?: number;
  trial_count?: number;
  patent_count?: number;
  cooccurrence_score?: number;
}

export interface JsonGraphPayload {
  center_node_id: string;
  nodes: JsonNode[];
  edges: JsonEdge[];
  message?: string;
}

export interface OverviewEntityPayload {
  id: string;
  name: string;
  type: string;
}

export interface OverviewEvidencePayload {
  id?: string;
  pmid?: string;
  title?: string;
  year?: number;
  snippet: string;
  source?: string;
  sourceDb?: string;
}

export interface OverviewEdgePayload {
  id: string;
  source: string;
  target: string;
  predicate: string;
  label?: string;
  score?: number;
  provenance: string;
  sourceDb: string;
  evidence: OverviewEvidencePayload[];
  paper_count?: number;
  trial_count?: number;
  patent_count?: number;
  cooccurrence_score?: number;
}

export interface OverviewHistoryPayload {
  selection_key: string;
  selection_type: "edge" | "node";
  summary: string;
}

export interface OverviewStreamRequestPayload {
  selection_type: "edge" | "node";
  edge_id?: string;
  node_id?: string;
  center_node_id: string;
  entities: OverviewEntityPayload[];
  edges: OverviewEdgePayload[];
  history: OverviewHistoryPayload[];
}

export interface OverviewCitation {
  id: string;
  kind: "evidence" | "rag";
  label: string;
}
