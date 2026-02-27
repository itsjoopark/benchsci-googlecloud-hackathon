import type { Entity } from "../types";
import type { JsonGraphPayload } from "../types/api";
import { jsonNodeToEntity } from "./adapters";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function queryEntity(
  query: string,
  signal?: AbortSignal
): Promise<JsonGraphPayload> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "Unknown error");
    throw new Error(
      res.status === 502
        ? "Entity extraction service is unavailable. Please try again."
        : `Query failed (${res.status}): ${detail}`
    );
  }
  return res.json();
}

export async function expandEntity(
  entityId: string,
  signal?: AbortSignal
): Promise<JsonGraphPayload> {
  const res = await fetch(`${API_BASE}/api/expand`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entity_id: entityId }),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "Unknown error");
    throw new Error(`Expand failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchGraph(): Promise<JsonGraphPayload> {
  const res = await fetch("/data_model.json");
  if (!res.ok) throw new Error("Failed to load graph data");
  return res.json();
}

export function searchGraph(
  query: string,
  payload: JsonGraphPayload
): Entity | null {
  const q = query.toLowerCase().trim();
  if (!q) return null;

  const node = payload.nodes.find((n) => {
    if (n.name.toLowerCase() === q) return true;
    if (n.name.toLowerCase().includes(q) || q.includes(n.name.toLowerCase()))
      return true;
    if (n.id.toLowerCase().includes(q)) return true;
    const meta = n.metadata as Record<string, unknown>;
    if (meta.symbol && String(meta.symbol).toLowerCase().includes(q))
      return true;
    if (meta.ncbi_gene_id && String(meta.ncbi_gene_id).includes(q))
      return true;
    if (Array.isArray(meta.aliases)) {
      if (meta.aliases.some((a: string) => a.toLowerCase().includes(q)))
        return true;
    }
    return false;
  });

  return node ? jsonNodeToEntity(node) : null;
}
