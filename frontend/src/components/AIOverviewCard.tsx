import { useEffect, useMemo, useRef, useState } from "react";
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

export default function AIOverviewCard({ request, onComplete }: Props) {
  const [rawText, setRawText] = useState("");
  const [visibleCount, setVisibleCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [citations, setCitations] = useState<OverviewCitation[]>([]);
  const [retryNonce, setRetryNonce] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const selectionKey = useMemo(
    () => (request ? getSelectionKey(request) : null),
    [request]
  );

  useEffect(() => {
    if (!request || !selectionKey) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    void streamOverview(request, {
      signal: controller.signal,
      onStart: () => {
        setRawText("");
        setVisibleCount(0);
        setError(null);
        setCitations([]);
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
        setRawText(finalText);
        setLoading(false);

        if (payload.citations?.length) {
          setCitations(payload.citations);
        }

        if (finalText.trim()) {
          onComplete({
            selectionKey,
            selectionType: request.selection_type,
            summary: finalText,
          });
        }
      },
      onError: (payload) => {
        if (payload.partial_text) {
          setRawText(payload.partial_text);
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
  }, [request, selectionKey, retryNonce, onComplete]);

  useEffect(() => {
    if (visibleCount >= rawText.length) return;
    const id = window.setInterval(() => {
      setVisibleCount((prev) => Math.min(rawText.length, prev + 3));
    }, 14);
    return () => window.clearInterval(id);
  }, [rawText, visibleCount]);

  const displayedText = rawText.slice(0, visibleCount);

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

      <div className={`ai-overview-body ${loading ? "streaming" : ""}`}>
        {displayedText ? (
          <p className="ai-overview-text">{displayedText}</p>
        ) : loading ? (
          <p className="ai-overview-placeholder">Building grounded explanation...</p>
        ) : (
          <p className="ai-overview-placeholder">Select a node or edge to generate context.</p>
        )}
      </div>

      {(error || citations.length > 0) && (
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

          {citations.length > 0 && (
            <div className="ai-overview-citations">
              {citations.slice(0, 10).map((citation) => (
                <span key={citation.id} className={`ai-overview-citation ${citation.kind}`}>
                  {citation.label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
