import type { Entity, GraphEdge } from "../types";
import { ENTITY_COLORS } from "../types";
import EntityCard from "./EntityCard";
import "./PathBreadcrumb.css";

interface Props {
  selectionHistory: Entity[];
  edges: GraphEdge[];
  onPrune: (index: number) => void;
  onClear: () => void;
}

/** Find the edge connecting two entities (in either direction). */
function findConnectingEdge(
  a: Entity,
  b: Entity,
  edges: GraphEdge[]
): GraphEdge | undefined {
  return edges.find(
    (e) =>
      (e.source === a.id && e.target === b.id) ||
      (e.target === a.id && e.source === b.id)
  );
}

/** SVG arrow connector between two cards. */
function PathArrow({ label }: { label?: string }) {
  return (
    <div className="path-arrow-connector">
      <div className="path-arrow-line" />
      {label && (
        <span className="path-arrow-label" title={label}>
          {label}
        </span>
      )}
      <svg className="path-arrow-head" width="12" height="8" viewBox="0 0 12 8">
        <path d="M0 0 L6 8 L12 0" fill="var(--color-text-secondary)" />
      </svg>
    </div>
  );
}

export default function PathBreadcrumb({
  selectionHistory,
  edges,
  onPrune,
  onClear,
}: Props) {
  if (selectionHistory.length === 0) return null;

  // selectionHistory is newest-first; reverse for chronological (oldest at top)
  const chronological = [...selectionHistory].reverse();

  return (
    <div className="path-breadcrumb">
      {chronological.map((entity, i) => {
        // Map reversed index back to the original newest-first index for pruning
        const originalIndex = selectionHistory.length - 1 - i;
        const prevEntity = i > 0 ? chronological[i - 1] : undefined;
        const connectingEdge = prevEntity
          ? findConnectingEdge(prevEntity, entity, edges)
          : undefined;

        const badgeColor = entity.color ?? ENTITY_COLORS[entity.type];

        return (
          <div key={entity.id} className="path-step">
            {/* Arrow connector between consecutive cards */}
            {i > 0 && (
              <PathArrow
                label={connectingEdge?.label ?? connectingEdge?.predicate}
              />
            )}

            {/* Compact entity card with prune button */}
            <div className="path-step-card" style={{ "--card-accent": badgeColor } as React.CSSProperties}>
              <EntityCard entity={entity} variant="compact" />
              <button
                className="path-step-prune"
                onClick={() => onPrune(originalIndex)}
                aria-label={`Remove ${entity.name} and newer entries`}
                title="Prune from here"
              >
                &times;
              </button>
            </div>
          </div>
        );
      })}

      <button className="path-breadcrumb-clear" onClick={onClear}>
        Clear history
      </button>
    </div>
  );
}
