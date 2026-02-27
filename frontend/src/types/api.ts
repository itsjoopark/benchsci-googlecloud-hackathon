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
  paper_count: number;
  trial_count: number;
  patent_count: number;
  cooccurrence_score: number;
}

export interface JsonGraphPayload {
  center_node_id: string;
  nodes: JsonNode[];
  edges: JsonEdge[];
  message?: string;
}
