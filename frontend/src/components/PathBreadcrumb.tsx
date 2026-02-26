import type { PathNode } from "../types";
import { ENTITY_COLORS } from "../types";
import "./PathBreadcrumb.css";

interface Props {
  path: PathNode[];
  onClear: () => void;
  onNodeClick: (nodeId: string) => void;
}

export default function PathBreadcrumb({ path, onClear, onNodeClick }: Props) {
  if (path.length === 0) return null;

  return (
    <div className="path-breadcrumb">
      <div className="path-trail">
        {path.map((node, i) => (
          <span key={node.entityId} className="path-segment">
            {i > 0 && <span className="path-arrow">→</span>}
            <button
              className="path-chip"
              style={{ borderColor: ENTITY_COLORS[node.entityType] }}
              onClick={() => onNodeClick(node.entityId)}
            >
              {node.entityName}
            </button>
          </span>
        ))}
      </div>
      <div className="path-actions">
        <button className="path-btn path-btn-save" disabled title="Coming soon">
          Save path
        </button>
        <button className="path-btn path-btn-clear" onClick={onClear}>
          Clear path
        </button>
      </div>
    </div>
  );
}
