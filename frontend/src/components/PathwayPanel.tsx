import type { Entity, GraphEdge, EvidenceItem } from "../types";
import { ENTITY_COLORS } from "../types";
import ProvenanceBadge from "./ProvenanceBadge";
import "./PathwayPanel.css";

interface Props {
  pathNodeIds: string[];
  entities: Entity[];
  edges: GraphEdge[];
  selectedEntityId: string | null;
  onEdgeSelect: (edgeId: string) => void;
}

/** Find the edge connecting two adjacent path nodes. */
function findPathEdge(
  a: string,
  b: string,
  edges: GraphEdge[]
): GraphEdge | undefined {
  return edges.find(
    (e) =>
      (e.source === a && e.target === b) ||
      (e.source === b && e.target === a)
  );
}

/** Collect all unique evidence items from a list of edges. */
function collectPathSources(pathEdges: GraphEdge[]): EvidenceItem[] {
  const seen = new Set<string>();
  const items: EvidenceItem[] = [];
  for (const edge of pathEdges) {
    for (const ev of edge.evidence ?? []) {
      const key = ev.pmid ?? ev.id;
      if (!seen.has(key)) {
        seen.add(key);
        items.push(ev);
      }
    }
  }
  items.sort((a, b) => {
    const aHas = a.title || a.snippet ? 1 : 0;
    const bHas = b.title || b.snippet ? 1 : 0;
    return bHas - aHas;
  });
  return items;
}

/** Use the title if available, otherwise extract the first sentence of the snippet. */
function getSourceTitle(item: EvidenceItem): string {
  if (item.title) return item.title;
  if (item.snippet) {
    const match = item.snippet.match(/^.+?[.!?](?:\s|$)/);
    return match ? match[0].trim() : item.snippet;
  }
  return item.pmid ? `PMID ${item.pmid}` : "Untitled";
}

export default function PathwayPanel({
  pathNodeIds,
  entities,
  edges,
  selectedEntityId,
  onEdgeSelect,
}: Props) {
  const entityMap = new Map(entities.map((e) => [e.id, e]));

  // Build the list of hops: each hop has a source entity, edge, and target entity
  const hops: { from: Entity; edge: GraphEdge | undefined; to: Entity }[] = [];
  for (let i = 0; i < pathNodeIds.length - 1; i++) {
    const from = entityMap.get(pathNodeIds[i]);
    const to = entityMap.get(pathNodeIds[i + 1]);
    if (from && to) {
      hops.push({ from, edge: findPathEdge(from.id, to.id, edges), to });
    }
  }

  const pathEdges = hops.map((h) => h.edge).filter((e): e is GraphEdge => !!e);
  const sources = collectPathSources(pathEdges);

  const startEntity = entityMap.get(pathNodeIds[0]);
  const endEntity = entityMap.get(pathNodeIds[pathNodeIds.length - 1]);

  return (
    <div className="pathway-panel">
      {/* Header */}
      <div className="pathway-header">
        <h2 className="pathway-title">Connection Pathway</h2>
        {startEntity && endEntity && (
          <div className="pathway-summary">
            <span
              className="pathway-entity-name"
              style={{ color: startEntity.color ?? ENTITY_COLORS[startEntity.type] }}
            >
              {startEntity.name}
            </span>
            <span className="pathway-arrow-inline">→</span>
            <span
              className="pathway-entity-name"
              style={{ color: endEntity.color ?? ENTITY_COLORS[endEntity.type] }}
            >
              {endEntity.name}
            </span>
          </div>
        )}
        <span className="pathway-hop-count">
          {hops.length} hop{hops.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="pathway-body">
        {/* Hop list */}
        <section className="pathway-section">
          <h3 className="pathway-section-title">Path Details</h3>
          <div className="pathway-hops">
            {hops.map((hop, i) => {
              const fromColor = hop.from.color ?? ENTITY_COLORS[hop.from.type];
              const toColor = hop.to.color ?? ENTITY_COLORS[hop.to.type];
              const edgeLabel = hop.edge?.label ?? hop.edge?.predicate?.replace(/_/g, " ") ?? "connected";
              const evidenceCount = hop.edge?.evidence?.length ?? 0;

              return (
                <div key={i} className="pathway-hop">
                  {/* Source node (only show for first hop) */}
                  {i === 0 && (
                    <div
                      className={`pathway-node${selectedEntityId === hop.from.id ? " selected" : ""}`}
                      style={{ "--node-color": fromColor } as React.CSSProperties}
                    >
                      <span className="pathway-node-type">{hop.from.type}</span>
                      <span className="pathway-node-name">{hop.from.name}</span>
                    </div>
                  )}

                  {/* Edge connector */}
                  <button
                    className={`pathway-edge-connector${hop.edge ? "" : " no-edge"}`}
                    onClick={() => hop.edge && onEdgeSelect(hop.edge.id)}
                    disabled={!hop.edge}
                    title={hop.edge ? "Click to view evidence" : "No edge data"}
                  >
                    <div className="pathway-edge-line" />
                    <div className="pathway-edge-info">
                      <span className="pathway-edge-label">{edgeLabel}</span>
                      <div className="pathway-edge-meta">
                        {evidenceCount > 0 && (
                          <span className="pathway-edge-evidence-count">
                            {evidenceCount} source{evidenceCount !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="pathway-edge-line" />
                  </button>

                  {/* Target node */}
                  <div
                    className={`pathway-node${selectedEntityId === hop.to.id ? " selected" : ""}`}
                    style={{ "--node-color": toColor } as React.CSSProperties}
                  >
                    <span className="pathway-node-type">{hop.to.type}</span>
                    <span className="pathway-node-name">{hop.to.name}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Aggregated sources from all path edges */}
        <section className="pathway-section">
          <h3 className="pathway-section-title">
            Sources ({sources.length})
          </h3>
          {sources.length === 0 ? (
            <p className="pathway-no-sources">
              No published evidence found for this pathway.
            </p>
          ) : (
            <div className="pathway-sources">
              {sources.map((item) => (
                <a
                  key={item.id}
                  className="pathway-source-card"
                  href={item.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${item.pmid}/` : undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <p className="pathway-source-title">{getSourceTitle(item)}</p>
                  <div className="pathway-source-footer">
                    {item.year != null && item.year > 0 && (
                      <span className="pathway-source-year">{item.year}</span>
                    )}
                    <ProvenanceBadge
                      type={item.sourceDb === "disgenet" ? "literature" : "curated"}
                    />
                    <span className="pathway-source-db">{item.sourceDb}</span>
                    {item.pmid && (
                      <span className="pathway-source-pmid">PMID {item.pmid}</span>
                    )}
                  </div>
                </a>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
