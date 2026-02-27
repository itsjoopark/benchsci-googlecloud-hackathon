import "./Toolbar.css";

interface Props {
  onFit: () => void;
  disabled: boolean;
  canReset: boolean;
  onReset: () => void;
  canShare?: boolean;
  onShare?: () => void;
  isSaving?: boolean;
}

export default function Toolbar({ onFit, disabled, canReset, onReset, canShare, onShare, isSaving }: Props) {
  return (
    <div className="toolbar">
      {canReset && (
        <button className="toolbar-reset-btn" onClick={onReset} title="Reset to initial query">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 4v6h6" />
            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
          </svg>
          Reset
        </button>
      )}
      {!disabled && (
        <button className="toolbar-fit-btn" onClick={onFit} title="Fit graph to screen">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 3 21 3 21 9"/>
            <polyline points="9 21 3 21 3 15"/>
            <line x1="21" y1="3" x2="14" y2="10"/>
            <line x1="3" y1="21" x2="10" y2="14"/>
          </svg>
          Fit
        </button>
      )}

      {canShare && (
        <button className="toolbar-share-btn" onClick={onShare} disabled={isSaving} title="Copy shareable link">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          {isSaving ? "Saving..." : "Share"}
        </button>
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
      </div>
    </div>
  );
}
