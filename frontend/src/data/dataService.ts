import type { Entity } from "../types";
import type { JsonGraphPayload } from "../types/api";
import { jsonPayloadToGraph, jsonNodeToEntity } from "./adapters";

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
