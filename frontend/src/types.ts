export type EntityType = "gene" | "disease" | "drug" | "pathway" | "protein";

export interface Entity {
  id: string;
  name: string;
  type: EntityType;
  primaryId: string;
  metadata: Record<string, string | number | string[] | undefined>;
  color?: string;
  size?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  predicate: string;
  label?: string;
  score?: number;
  provenance: "curated" | "literature" | "inferred";
  sourceDb: string;
  evidence?: EvidenceItem[];
  color?: string;
  paperCount?: number;
  trialCount?: number;
  patentCount?: number;
  cooccurrenceScore?: number;
}

export interface EvidenceItem {
  id: string;
  pmid?: string;
  title?: string;
  year?: number;
  snippet: string;
  source: string;
  sourceDb: string;
}

export const ENTITY_COLORS: Record<EntityType, string> = {
  gene: "#4A90D9",
  disease: "#E74C3C",
  drug: "#2ECC71",
  pathway: "#F39C12",
  protein: "#9B59B6",
};

export const ENTITY_SHAPES: Record<EntityType, string> = {
  gene: "ellipse",
  disease: "diamond",
  drug: "round-rectangle",
  pathway: "hexagon",
  protein: "triangle",
};

export type EntityFilterValue = EntityType[] | "all";
