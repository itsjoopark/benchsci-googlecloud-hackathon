import type { Entity, GraphEdge, EntityFilterValue } from "../types";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "https://benchspark-backend-s7fuxsjnxq-uc.a.run.app";

const LS_PREFIX = "biorender_snapshot_";

export interface GraphSnapshot {
  query: string;
  entities: Entity[];
  edges: GraphEdge[];
  expanded_nodes: string[];
  center_node_id: string;
  path_node_ids: string[];
  entity_filter: EntityFilterValue;
  node_positions: Record<string, { x: number; y: number }>;
  selection_history: Entity[];
  selected_entity_id: string | null;
}

function generateId(): string {
  return Math.random().toString(36).slice(2, 10);
}

/**
 * Save snapshot — tries backend first, falls back to localStorage.
 * Returns the snapshot ID.
 */
export async function saveSnapshot(snapshot: GraphSnapshot): Promise<string> {
  // Try backend first
  try {
    const res = await fetch(`${API_BASE}/api/graph/snapshot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    });
    if (res.ok) {
      const data = await res.json();
      return data.id as string;
    }
  } catch {
    // Backend unavailable — fall through to localStorage
  }

  // Fallback: localStorage
  const id = generateId();
  localStorage.setItem(LS_PREFIX + id, JSON.stringify(snapshot));
  return id;
}

/**
 * Load snapshot — tries backend first, falls back to localStorage.
 */
export async function loadSnapshot(id: string): Promise<GraphSnapshot | null> {
  // Try backend first
  try {
    const res = await fetch(`${API_BASE}/api/graph/snapshot/${id}`);
    if (res.ok) {
      return res.json();
    }
  } catch {
    // Backend unavailable — fall through to localStorage
  }

  // Fallback: localStorage
  const raw = localStorage.getItem(LS_PREFIX + id);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as GraphSnapshot;
  } catch {
    return null;
  }
}
