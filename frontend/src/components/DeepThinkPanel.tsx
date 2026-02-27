import { useCallback, useRef, useState } from "react";
import type { GraphEdge, PathNode } from "../types";
import { streamDeepThink } from "../data/dataService";
import type { DeepThinkPaper, DeepThinkRequestPayload } from "../types/api";
import "./DeepThinkPanel.css";

interface Props {
  path: PathNode[];
  edges: GraphEdge[];
}

type Status = "idle" | "loading" | "streaming" | "done" | "error";

export default function DeepThinkPanel({ path, edges }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [analysisText, setAnalysisText] = useState("");
  const [papers, setPapers] = useState<DeepThinkPaper[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleAnalyze = useCallback(async () => {
    if (path.length < 2) return;

    // Cancel any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("loading");
    setAnalysisText("");
    setPapers([]);
    setErrorMsg(null);

    // Build edges for consecutive path pairs
    const pathEdges: DeepThinkRequestPayload["edges"] = [];
    for (let i = 0; i < path.length - 1; i++) {
      const srcId = path[i].entityId;
      const tgtId = path[i + 1].entityId;
      const matching = edges.find(
        (e) =>
          (e.source === srcId && e.target === tgtId) ||
          (e.target === srcId && e.source === tgtId)
      );
      if (matching) {
        pathEdges.push({
          source: matching.source,
          target: matching.target,
          predicate: matching.predicate,
          evidence: (matching.evidence ?? []).map((ev) => ({
            pmid: ev.pmid,
            title: ev.title,
            snippet: ev.snippet,
          })),
        });
      }
    }

    const request: DeepThinkRequestPayload = {
      path: path.map((n) => ({
        entity_id: n.entityId,
        entity_name: n.entityName,
        entity_type: n.entityType,
        edge_predicate: n.edgePredicate,
      })),
      edges: pathEdges,
    };

    try {
      await streamDeepThink(request, {
        signal: controller.signal,
        onStart: () => {
          setStatus("loading");
        },
        onPapersLoaded: ({ papers: loaded }) => {
          setPapers(loaded);
          setStatus("streaming");
        },
        onDelta: ({ text }) => {
          setStatus("streaming");
          setAnalysisText((prev) => prev + text);
        },
        onDone: ({ text }) => {
          if (text) setAnalysisText(text);
          setStatus("done");
        },
        onError: ({ message, partial_text }) => {
          if (partial_text) setAnalysisText(partial_text);
          setErrorMsg(message);
          setStatus("error");
        },
      });
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      setErrorMsg(err instanceof Error ? err.message : "Deep Think failed.");
      setStatus("error");
    }
  }, [path, edges]);

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    setStatus("idle");
    setAnalysisText("");
    setPapers([]);
    setErrorMsg(null);
  }, []);

  if (path.length < 2) return null;

  const pathSummary = path.map((n) => n.entityName).join(" → ");

  return (
    <section className="deep-think-panel" aria-live="polite">
      <div className="deep-think-header">
        <div className="deep-think-title-wrap">
          <span className="deep-think-icon" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a10 10 0 1 0 10 10" />
              <path d="M12 6v6l4 2" />
              <path d="M20 2l-1.5 1.5" />
              <path d="M22 8h-2" />
              <path d="M20 14l-1.5-1.5" />
            </svg>
          </span>
          <h3 className="deep-think-title">Deep Think</h3>
          {status === "streaming" && (
            <span className="deep-think-status">Analyzing...</span>
          )}
          {status === "done" && (
            <span className="deep-think-status done">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Done
            </span>
          )}
        </div>
        <div className="deep-think-header-actions">
          {(status === "done" || status === "error" || status === "streaming") && (
            <button
              className="deep-think-reset"
              onClick={handleReset}
              aria-label="Reset analysis"
              title="Reset"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      <div className="deep-think-path-summary">
        {pathSummary}
      </div>

      {status === "idle" && (
        <button className="deep-think-analyze-btn" onClick={handleAnalyze}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
          Analyze Path
        </button>
      )}

      {status === "loading" && (
        <div className="deep-think-loading">
          <div className="deep-think-spinner" />
          <span>Fetching papers...</span>
        </div>
      )}

      {(status === "streaming" || status === "done" || status === "error") && (
        <>
          {papers.length > 0 && (
            <div className="deep-think-citations">
              <h4 className="deep-think-citations-title">Supporting Papers</h4>
              <ol className="deep-think-citations-list">
                {papers.map((paper, i) => (
                  <li key={i} className="deep-think-citation-item">
                    {paper.pmid ? (
                      <a
                        href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="deep-think-citation-link"
                      >
                        {paper.title}
                      </a>
                    ) : (
                      <span className="deep-think-citation-link">{paper.title}</span>
                    )}
                    {paper.year && (
                      <span className="deep-think-citation-year">{paper.year}</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {(analysisText || status === "streaming") && (
            <div className={`deep-think-body ${status === "streaming" ? "streaming" : ""}`}>
              {analysisText ? (
                <p className="deep-think-text">{analysisText}</p>
              ) : (
                <p className="deep-think-placeholder">Generating analysis...</p>
              )}
            </div>
          )}

          {errorMsg && (
            <div className="deep-think-error-row">
              <span className="deep-think-error">{errorMsg}</span>
              <button className="deep-think-retry" onClick={handleAnalyze}>
                Retry
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
