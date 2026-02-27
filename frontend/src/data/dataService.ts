import type { Entity } from "../types";
import type {
  DeepThinkPaper,
  DeepThinkRequestPayload,
  JsonGraphPayload,
  OverviewCitation,
  OverviewStreamRequestPayload,
} from "../types/api";
import { jsonNodeToEntity } from "./adapters";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "https://benchspark-backend-s7fuxsjnxq-uc.a.run.app";

export async function queryEntity(
  query: string,
  signal?: AbortSignal
): Promise<JsonGraphPayload> {
  const MAX_RETRIES = 2;
  const RETRY_DELAY_MS = 1500;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const res = await fetch(`${API_BASE}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal,
    });
    if (res.ok) return res.json();

    // Retry on 502 (cold-start / transient gateway error)
    if (res.status === 502 && attempt < MAX_RETRIES) {
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
      continue;
    }

    const detail = await res.text().catch(() => "Unknown error");
    throw new Error(
      res.status === 502
        ? "Entity extraction service is unavailable. Please try again."
        : `Query failed (${res.status}): ${detail}`
    );
  }

  throw new Error("Query failed after retries.");
}

export async function expandEntity(
  entityId: string,
  signal?: AbortSignal
): Promise<JsonGraphPayload> {
  const MAX_RETRIES = 2;
  const RETRY_DELAY_MS = 1500;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const res = await fetch(`${API_BASE}/api/expand`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entity_id: entityId }),
      signal,
    });
    if (res.ok) return res.json();

    if (res.status === 502 && attempt < MAX_RETRIES) {
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
      continue;
    }

    const detail = await res.text().catch(() => "Unknown error");
    throw new Error(`Expand failed (${res.status}): ${detail}`);
  }

  throw new Error("Expand failed after retries.");
}

export async function fetchGraph(): Promise<JsonGraphPayload> {
  const res = await fetch("/data_model.json");
  if (!res.ok) throw new Error("Failed to load graph data");
  return res.json();
}

interface OverviewStreamHandlers {
  onStart?: (payload: Record<string, unknown>) => void;
  onContext?: (payload: {
    citations?: OverviewCitation[];
    rag_chunks?: Array<Record<string, unknown>>;
  }) => void;
  onDelta?: (payload: { text: string }) => void;
  onDone?: (payload: {
    text: string;
    citations?: OverviewCitation[];
    selection_key?: string;
    selection_type?: "edge" | "node";
  }) => void;
  onError?: (payload: { message: string; partial_text?: string }) => void;
  signal?: AbortSignal;
}

function parseSseBlock(
  block: string
): { event: string; data: Record<string, unknown> } | null {
  const lines = block.split("\n");
  let event = "";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!event || dataLines.length === 0) return null;

  try {
    return {
      event,
      data: JSON.parse(dataLines.join("\n")) as Record<string, unknown>,
    };
  } catch {
    return null;
  }
}

export async function streamOverview(
  request: OverviewStreamRequestPayload,
  handlers: OverviewStreamHandlers
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/overview/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: handlers.signal,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "Unknown error");
    throw new Error(`Overview stream failed (${res.status}): ${detail}`);
  }

  if (!res.body) {
    throw new Error("Overview stream response body is empty.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block.trim());
      if (!parsed) continue;

      if (parsed.event === "start") {
        handlers.onStart?.(parsed.data);
      } else if (parsed.event === "context") {
        handlers.onContext?.({
          citations: parsed.data.citations as OverviewCitation[] | undefined,
          rag_chunks: parsed.data.rag_chunks as Array<Record<string, unknown>> | undefined,
        });
      } else if (parsed.event === "delta") {
        handlers.onDelta?.({ text: String(parsed.data.text ?? "") });
      } else if (parsed.event === "done") {
        handlers.onDone?.({
          text: String(parsed.data.text ?? ""),
          citations: parsed.data.citations as OverviewCitation[] | undefined,
          selection_key: parsed.data.selection_key as string | undefined,
          selection_type: parsed.data.selection_type as "edge" | "node" | undefined,
        });
      } else if (parsed.event === "error") {
        handlers.onError?.({
          message: String(parsed.data.message ?? "Overview generation failed."),
          partial_text: parsed.data.partial_text as string | undefined,
        });
      }
    }
  }

  const finalBlock = parseSseBlock(buffer.trim());
  if (!finalBlock) return;

  if (finalBlock.event === "done") {
    handlers.onDone?.({
      text: String(finalBlock.data.text ?? ""),
      citations: finalBlock.data.citations as OverviewCitation[] | undefined,
      selection_key: finalBlock.data.selection_key as string | undefined,
      selection_type: finalBlock.data.selection_type as "edge" | "node" | undefined,
    });
  } else if (finalBlock.event === "error") {
    handlers.onError?.({
      message: String(finalBlock.data.message ?? "Overview generation failed."),
      partial_text: finalBlock.data.partial_text as string | undefined,
    });
  }
}

interface DeepThinkStreamHandlers {
  onStart?: (payload: { path_summary: string; node_count: number }) => void;
  onPapersLoaded?: (payload: { papers: DeepThinkPaper[]; count: number }) => void;
  onDelta?: (payload: { text: string }) => void;
  onDone?: (payload: { text: string }) => void;
  onError?: (payload: { message: string; partial_text?: string }) => void;
  signal?: AbortSignal;
}

export async function streamDeepThink(
  request: DeepThinkRequestPayload,
  handlers: DeepThinkStreamHandlers
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/deep-think/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: handlers.signal,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "Unknown error");
    throw new Error(`Deep Think stream failed (${res.status}): ${detail}`);
  }

  if (!res.body) {
    throw new Error("Deep Think stream response body is empty.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block.trim());
      if (!parsed) continue;

      if (parsed.event === "start") {
        handlers.onStart?.({
          path_summary: String(parsed.data.path_summary ?? ""),
          node_count: Number(parsed.data.node_count ?? 0),
        });
      } else if (parsed.event === "papers_loaded") {
        handlers.onPapersLoaded?.({
          papers: (parsed.data.papers as DeepThinkPaper[]) ?? [],
          count: Number(parsed.data.count ?? 0),
        });
      } else if (parsed.event === "delta") {
        handlers.onDelta?.({ text: String(parsed.data.text ?? "") });
      } else if (parsed.event === "done") {
        handlers.onDone?.({ text: String(parsed.data.text ?? "") });
      } else if (parsed.event === "error") {
        handlers.onError?.({
          message: String(parsed.data.message ?? "Deep Think generation failed."),
          partial_text: parsed.data.partial_text as string | undefined,
        });
      }
    }
  }

  const finalBlock = parseSseBlock(buffer.trim());
  if (!finalBlock) return;

  if (finalBlock.event === "done") {
    handlers.onDone?.({ text: String(finalBlock.data.text ?? "") });
  } else if (finalBlock.event === "error") {
    handlers.onError?.({
      message: String(finalBlock.data.message ?? "Deep Think generation failed."),
      partial_text: finalBlock.data.partial_text as string | undefined,
    });
  }
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
