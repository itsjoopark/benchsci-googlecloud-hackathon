import "./Toolbar.css";

interface Props {
  onFit: () => void;
  disabled: boolean;
}

export default function Toolbar({ onFit, disabled }: Props) {
  return (
    <div className="toolbar">
      <button className="toolbar-btn" disabled={disabled} onClick={onFit} title="Fit to screen">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
        </svg>
      </button>
      <span className="toolbar-hint">
        Click node to select &middot; Double-click to expand &middot; Right-click to add to path
      </span>
    </div>
  );
}
