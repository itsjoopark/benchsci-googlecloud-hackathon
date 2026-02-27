import type { Entity, GraphEdge, EvidenceItem } from "../types";
import { ENTITY_COLORS } from "../types";
import ProvenanceBadge from "./ProvenanceBadge";
import "./EvidencePanel.css";

interface Props {
  edge: GraphEdge;
  evidence: EvidenceItem[];
  entities: Entity[];
  onClose: () => void;
  onCollapse?: () => void;
}

export default function EvidencePanel({ edge, evidence, entities, onClose, onCollapse }: Props) {
  const source = entities.find((e) => e.id === edge.source);
  const target = entities.find((e) => e.id === edge.target);
  const sourceColor = source?.color ?? (source ? ENTITY_COLORS[source.type] : undefined);
  const targetColor = target?.color ?? (target ? ENTITY_COLORS[target.type] : undefined);

  const connectionLabel = edge.label ?? edge.predicate.replace(/_/g, " ");
  const confidencePct =
    edge.score !== undefined ? `${(edge.score * 100).toFixed(0)}%` : null;

  return (
    <div className="evidence-panel">
      {/* Header */}
      <div className="evidence-header">
        <div className="evidence-header-top">
          <h2 className="evidence-title">Evidence</h2>
          <div className="evidence-header-actions">
            {onCollapse && (
              <button className="close-btn" onClick={onCollapse} aria-label="Collapse">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 18l6-6-6-6" />
                </svg>
              </button>
            )}
            <button className="close-btn" onClick={onClose} aria-label="Close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Connection summary */}
        <div className="connection-summary">
          <span
            className="connection-entity"
            style={{ color: sourceColor }}
          >
            {source?.name || edge.source}
          </span>
          <span className="connection-arrow">→</span>
          <span
            className="connection-entity"
            style={{ color: targetColor }}
          >
            {target?.name || edge.target}
          </span>
        </div>

        <div className="connection-meta">
          <span className="predicate-label">{connectionLabel}</span>
          {confidencePct && (
            <span className="confidence-score">Score: {confidencePct}</span>
          )}
          <ProvenanceBadge type={edge.provenance} />
        </div>
      </div>

      {/* Evidence list */}
      <div className="evidence-list">
        {evidence.length === 0 ? (
          <p className="no-evidence">
            No published evidence found. This connection is based on {edge.sourceDb} curation.
          </p>
        ) : (
          evidence.map((item) => (
            <div key={item.id} className="evidence-card">
              <div className="evidence-card-header">
                {item.pmid && (
                  <a
                    className="pmid-link"
                    href={`https://pubmed.ncbi.nlm.nih.gov/${item.pmid}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    PMID: {item.pmid}
                  </a>
                )}
                {item.year && <span className="evidence-year">{item.year}</span>}
              </div>
              {item.title && item.title !== item.snippet && (
                <p className="evidence-card-title">{item.title}</p>
              )}
              <p className="evidence-snippet">{item.snippet}</p>
              <div className="evidence-card-footer">
                <ProvenanceBadge type={item.sourceDb === "disgenet" ? "literature" : "curated"} />
                <span className="source-db">{item.sourceDb}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
