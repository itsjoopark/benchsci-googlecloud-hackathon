import type { Entity, GraphEdge, EvidenceItem } from "../types";
import { getEntityResearch } from "../data/entityResearch";
import "./EntityAdvancedSearchPanel.css";

interface Props {
  entity: Entity;
  selectionHistory: Entity[];
  edges: GraphEdge[];
  onCollapse: () => void;
}

function getOverviewSectionTitle(entityType: string): string {
  const map: Record<string, string> = {
    gene: "Gene Overview",
    disease: "Disease Overview",
    drug: "Drug Overview",
    pathway: "Pathway Overview",
    protein: "Protein Overview",
  };
  return map[entityType] ?? "Overview";
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

function collectSourcesFromEdges(entityId: string, edges: GraphEdge[]): EvidenceItem[] {
  const seen = new Set<string>();
  const items: EvidenceItem[] = [];
  for (const edge of edges) {
    if (edge.source !== entityId && edge.target !== entityId) continue;
    for (const ev of edge.evidence ?? []) {
      if (ev.pmid && !seen.has(ev.pmid)) {
        seen.add(ev.pmid);
        items.push(ev);
      }
    }
  }
  // Show sources with titles/snippets first, then the rest
  items.sort((a, b) => {
    const aHas = a.title || a.snippet ? 1 : 0;
    const bHas = b.title || b.snippet ? 1 : 0;
    return bHas - aHas;
  });
  return items;
}

function findConnectingEdge(
  entityA: string,
  entityB: string,
  edges: GraphEdge[]
): GraphEdge | undefined {
  return edges.find(
    (e) =>
      (e.source === entityA && e.target === entityB) ||
      (e.source === entityB && e.target === entityA)
  );
}

export default function EntityAdvancedSearchPanel({
  entity,
  selectionHistory,
  edges,
  onCollapse,
}: Props) {
  const research = getEntityResearch(entity.id);
  const sources = collectSourcesFromEdges(entity.id, edges);
  const overviewTitle = getOverviewSectionTitle(entity.type);

  // Find all history nodes (excluding the current entity) that have a connecting edge
  const cooccurrenceEntries = selectionHistory
    .filter((h) => h.id !== entity.id)
    .map((h) => ({ historyEntity: h, edge: findConnectingEdge(entity.id, h.id, edges) }))
    .filter((entry): entry is { historyEntity: Entity; edge: GraphEdge } => entry.edge !== undefined);

  return (
    <div className="entity-advanced-search-panel">
      <div className="entity-advanced-search-header">
        <h2 className="entity-advanced-search-title">
          {entity.name} Advanced Search
        </h2>
        <button
          className="entity-advanced-search-collapse"
          onClick={onCollapse}
          aria-label="Collapse sidebar"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      </div>

      <div className="entity-advanced-search-body">
        {/* Co-occurrence stats for all connected history nodes */}
        {cooccurrenceEntries.map(({ historyEntity, edge }) => (
          <section key={historyEntity.id} className="entity-advanced-search-section">
            <h3 className="entity-advanced-search-section-title">
              Co-occurrence with {historyEntity.name}
            </h3>
            <div className="cooccurrence-stats">
              <div className="cooccurrence-stat">
                <span className="cooccurrence-stat-icon">📄</span>
                <span className="cooccurrence-stat-value">
                  {edge.paperCount?.toLocaleString() ?? "—"}
                </span>
                <span className="cooccurrence-stat-label">Papers</span>
              </div>
              <div className="cooccurrence-stat">
                <span className="cooccurrence-stat-icon">🧪</span>
                <span className="cooccurrence-stat-value">
                  {edge.trialCount?.toLocaleString() ?? "—"}
                </span>
                <span className="cooccurrence-stat-label">Trials</span>
              </div>
              <div className="cooccurrence-stat">
                <span className="cooccurrence-stat-icon">📋</span>
                <span className="cooccurrence-stat-value">
                  {edge.patentCount?.toLocaleString() ?? "—"}
                </span>
                <span className="cooccurrence-stat-label">Patents</span>
              </div>
            </div>
            {edge.label && (
              <p className="cooccurrence-relation">
                Relationship: <strong>{edge.label}</strong>
              </p>
            )}
          </section>
        ))}

        {/* Sources */}
        <section className="entity-advanced-search-section">
          <h3 className="entity-advanced-search-section-title">
            Sources ({sources.length})
          </h3>
          {sources.length === 0 ? (
            <p className="entity-advanced-search-no-sources">
              No sources found for this entity.
            </p>
          ) : (
            <div className="entity-advanced-search-sources">
              {sources.map((item) => (
                <a
                  key={item.id}
                  className="entity-advanced-search-source-card"
                  href={`https://pubmed.ncbi.nlm.nih.gov/${item.pmid}/`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <p className="entity-advanced-search-source-title">
                    {getSourceTitle(item)}
                  </p>
                  <div className="entity-advanced-search-source-footer">
                    {item.year != null && item.year > 0 && (
                      <span className="entity-advanced-search-source-year">{item.year}</span>
                    )}
                    <span className="entity-advanced-search-source-link">PubMed ↗</span>
                  </div>
                </a>
              ))}
            </div>
          )}
        </section>

        {/* Overview */}
        <section className="entity-advanced-search-section">
          <h3 className="entity-advanced-search-section-title">
            {overviewTitle}
          </h3>
          <p className="entity-advanced-search-overview">
            {research?.overview ??
              (entity.metadata.full_name
                ? String(entity.metadata.full_name)
                : `No detailed overview available for ${entity.name}.`)}
          </p>
        </section>

        {/* Clinical Relevance */}
        <section className="entity-advanced-search-section">
          <h3 className="entity-advanced-search-section-title">
            Clinical Relevance
          </h3>
          {research?.clinicalRelevance &&
          research.clinicalRelevance.length > 0 ? (
            <ul className="entity-advanced-search-clinical-list">
              {research.clinicalRelevance.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="entity-advanced-search-no-clinical">
              No clinical relevance data available for this entity.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
