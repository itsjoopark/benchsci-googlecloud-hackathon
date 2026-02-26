import type { Entity, GraphEdge, EvidenceItem } from "../types";
import { getEntityResearch } from "../data/entityResearch";
import "./EntityAdvancedSearchPanel.css";

interface Props {
  entity: Entity;
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
  return items;
}

export default function EntityAdvancedSearchPanel({
  entity,
  edges,
  onCollapse,
}: Props) {
  const research = getEntityResearch(entity.id);
  const sources = collectSourcesFromEdges(entity.id, edges);
  const overviewTitle = getOverviewSectionTitle(entity.type);

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
                  <div className="entity-advanced-search-source-thumb">
                    <span className="entity-advanced-search-source-icon">📄</span>
                  </div>
                  <div className="entity-advanced-search-source-meta">
                    <span className="entity-advanced-search-source-pmid">
                      PubMed.ncbi.nlm.nih.gov
                    </span>
                    {item.pmid && (
                      <span className="entity-advanced-search-source-id">
                        PMID: {item.pmid}
                      </span>
                    )}
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
