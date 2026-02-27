import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { streamOverview } from "../data/dataService";
import type {
  OverviewCitation,
  OverviewStreamRequestPayload,
} from "../types/api";
import "./AIOverviewCard.css";

interface Props {
  request: OverviewStreamRequestPayload | null;
  onComplete: (item: {
    selectionKey: string;
    selectionType: "edge" | "node";
    summary: string;
  }) => void;
}

function getSelectionKey(request: OverviewStreamRequestPayload): string {
  if (request.selection_type === "edge") {
    return `edge:${request.edge_id ?? "unknown"}`;
  }
  return `node:${request.node_id ?? "unknown"}`;
}

function normalizeCitationLabel(label: string): string {
  return label.trim().replace(/^\[|\]$/g, "");
}

function parseInlineCitations(text: string): { body: string; citations: string[] } {
  const tailCitationsMatch = text.match(/\bCitations:\s*((?:\[[^\]]+\]\s*,?\s*)+)$/i);
  if (!tailCitationsMatch || tailCitationsMatch.index === undefined) {
    return { body: text, citations: [] };
  }

  const body = text.slice(0, tailCitationsMatch.index).trimEnd();
  const citationBlock = tailCitationsMatch[1] ?? "";
  const citations = Array.from(citationBlock.matchAll(/\[([^\]]+)\]/g)).map((m) =>
    normalizeCitationLabel(m[1] ?? "")
  );
  return { body, citations };
}

function renderRichText(text: string): ReactNode[] {
  const lines = text.split("\n");
  const tokenRegex = /(\*\*[^*]+\*\*|\(score\s*=\s*[0-9.]+\)|\[[^\]]+\])/gi;

  return lines.map((line, lineIndex) => {
    const nodes: ReactNode[] = [];
    let last = 0;

    for (const match of line.matchAll(tokenRegex)) {
      const token = match[0];
      const idx = match.index ?? 0;
      if (idx > last) {
        nodes.push(line.slice(last, idx));
      }

      if (/^\*\*[^*]+\*\*$/.test(token)) {
        nodes.push(
          <strong key={`strong-${lineIndex}-${idx}`}>
            {token.slice(2, -2)}
          </strong>
        );
      } else if (/^\(score\s*=\s*[0-9.]+\)$/i.test(token)) {
        nodes.push(
          <span key={`score-${lineIndex}-${idx}`} className="ai-score-tag">
            {token}
          </span>
        );
      } else {
        nodes.push(
          <span key={`cite-${lineIndex}-${idx}`} className="ai-inline-citation">
            {token}
          </span>
        );
      }
      last = idx + token.length;
    }

    if (last < line.length) {
      nodes.push(line.slice(last));
    }

    return (
      <span key={`line-${lineIndex}`}>
        {nodes}
        {lineIndex < lines.length - 1 ? <br /> : null}
      </span>
    );
  });
}

export default function AIOverviewCard({ request, onComplete }: Props) {
  const [rawText, setRawText] = useState("");
  const [visibleCount, setVisibleCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [citations, setCitations] = useState<OverviewCitation[]>([]);
  const [retryNonce, setRetryNonce] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const requestRef = useRef<OverviewStreamRequestPayload | null>(null);
  const onCompleteRef = useRef(onComplete);

  const selectionKey = useMemo(
    () => (request ? getSelectionKey(request) : null),
    [request]
  );
  const streamKey = useMemo(() => {
    if (!request || !selectionKey) return null;
    return `${request.selection_type}:${selectionKey}:${request.center_node_id}`;
  }, [request, selectionKey]);

  useEffect(() => {
    requestRef.current = request;
  }, [request]);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    const activeRequest = requestRef.current;
    if (!activeRequest || !selectionKey || !streamKey) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    void streamOverview(activeRequest, {
      signal: controller.signal,
      onStart: () => {
        setRawText("");
        setVisibleCount(0);
        setError(null);
        setCitations([]);
        setCollapsed(false);
        setLoading(true);
      },
      onContext: (payload) => {
        setCitations(payload.citations ?? []);
      },
      onDelta: ({ text }) => {
        setRawText((prev) => prev + text);
      },
      onDone: (payload) => {
        const finalText = payload.text || "";
        // Never shrink text on done: keep streaming deltas if they're longer.
        setRawText((prev) => {
          const merged = finalText.length > prev.length ? finalText : prev;
          setVisibleCount(merged.length);
          return merged;
        });
        setLoading(false);

        if (payload.citations?.length) {
          setCitations(payload.citations);
        }

        if (finalText.trim()) {
          onCompleteRef.current({
            selectionKey,
            selectionType: activeRequest.selection_type,
            summary: finalText,
          });
        }
      },
      onError: (payload) => {
        if (payload.partial_text) {
          setRawText(payload.partial_text);
          setVisibleCount(payload.partial_text.length);
        }
        setError(payload.message);
        setLoading(false);
      },
    }).catch((err: unknown) => {
      if (err instanceof Error && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to stream AI overview.");
      setLoading(false);
    });

    return () => {
      controller.abort();
    };
  }, [selectionKey, streamKey, retryNonce]);

  useEffect(() => {
    if (visibleCount >= rawText.length) return;
    const id = window.setInterval(() => {
      setVisibleCount((prev) => Math.min(rawText.length, prev + 3));
    }, 14);
    return () => window.clearInterval(id);
  }, [rawText, visibleCount]);

  const displayedText = rawText.slice(0, visibleCount);
  const canCollapse = displayedText.length > 260 || displayedText.includes("\n");
  const parsed = useMemo(() => parseInlineCitations(displayedText), [displayedText]);
  const parsedCitationLabels = useMemo(() => {
    const labelSet = new Set<string>();
    for (const c of citations) {
      labelSet.add(normalizeCitationLabel(c.label));
    }
    for (const c of parsed.citations) {
      labelSet.add(normalizeCitationLabel(c));
    }
    return Array.from(labelSet).filter(Boolean);
  }, [citations, parsed.citations]);

  return (
    <section className="ai-overview-card" aria-live="polite">
      <div className="ai-overview-header">
        <div className="ai-overview-title-wrap">
          <span className="ai-overview-spark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <h3 className="ai-overview-title">AI Overview</h3>
        </div>
        {loading && <span className="ai-overview-status">Streaming...</span>}
      </div>

      <div
        className={`ai-overview-body ${loading ? "streaming" : ""} ${collapsed ? "collapsed" : ""}`}
      >
        {parsed.body ? (
          <p className={`ai-overview-text ${loading ? "streaming" : ""}`}>
            {renderRichText(parsed.body)}
          </p>
        ) : loading ? (
          <p className="ai-overview-placeholder">Building grounded explanation...</p>
        ) : (
          <p className="ai-overview-placeholder">Select a node or edge to generate context.</p>
        )}
      </div>

      {(error || parsedCitationLabels.length > 0 || canCollapse) && (
        <div className="ai-overview-footer">
          {error && (
            <div className="ai-overview-error-row">
              <span className="ai-overview-error">{error}</span>
              <button
                className="ai-overview-retry"
                onClick={() => setRetryNonce((n) => n + 1)}
              >
                Retry
              </button>
            </div>
          )}

          {parsedCitationLabels.length > 0 && (
            <div className="ai-overview-citations">
              <h4 className="ai-overview-citations-label">Citations</h4>
              {parsedCitationLabels.slice(0, 12).map((label) => (
                <span key={label} className="ai-overview-citation evidence">
                  {label}
                </span>
              ))}
            </div>
          )}

          {canCollapse && (
            <div className="ai-overview-toggle-row">
              <button
                type="button"
                className="ai-overview-toggle"
                onClick={() => setCollapsed((prev) => !prev)}
                aria-expanded={!collapsed}
                aria-label={collapsed ? "Expand AI overview" : "Collapse AI overview"}
                title={collapsed ? "Expand overview" : "Collapse overview"}
              >
                <span className={`ai-overview-toggle-arrow ${collapsed ? "down" : "up"}`}>
                  {collapsed ? "↓" : "↑"}
                </span>
                <span className="ai-overview-toggle-label">
                  {collapsed ? "Show full overview" : "Collapse overview"}
                </span>
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
