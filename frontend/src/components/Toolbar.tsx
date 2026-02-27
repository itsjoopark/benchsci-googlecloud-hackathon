import "./Toolbar.css";

interface Props {
  onFit: () => void;
  disabled: boolean;
  pathLength: number;
  onClearPath: () => void;
}

export default function Toolbar({ onFit, disabled, pathLength, onClearPath }: Props) {
  return (
    <div className="toolbar">
      <button className="toolbar-btn" disabled={disabled} onClick={onFit} title="Fit to screen">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
        </svg>
      </button>
      <button
        className={`toolbar-btn toolbar-btn-clear-path ${pathLength > 0 ? "active" : ""}`}
        disabled={pathLength === 0}
        onClick={onClearPath}
        title="Clear path"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </svg>
      </button>
      {pathLength > 0 && (
        <span className="toolbar-path-count">{pathLength} in path</span>
      )}
      <span className="toolbar-hint">
        Click node to select &middot; Double-click to expand &middot; Right-click to add to path
      </span>
    </div>
  );
}
