import "./Toolbar.css";

interface Props {
  onFit: () => void;
  disabled: boolean;
  pathLength: number;
  onClearPath: () => void;
}

export default function Toolbar({ pathLength }: Props) {
  return (
    <div className="toolbar">
      {pathLength > 0 && (
        <span className="toolbar-path-count">{pathLength} in path</span>
      )}
      <div className="toolbar-hints">
        <span className="toolbar-hint-item">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 15l-2 5L9 9l11 4-5 2z" />
          </svg>
          Click to select
        </span>
        <span className="toolbar-hint-separator">&middot;</span>
        <span className="toolbar-hint-item toolbar-hint-expand">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 3 21 3 21 9" />
            <polyline points="9 21 3 21 3 15" />
            <line x1="21" y1="3" x2="14" y2="10" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
          Double-click to expand
        </span>
        <span className="toolbar-hint-separator">&middot;</span>
        <span className="toolbar-hint-item">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="1" />
            <circle cx="19" cy="12" r="1" />
            <circle cx="5" cy="12" r="1" />
          </svg>
          Right-click to path
        </span>
      </div>
    </div>
  );
}
