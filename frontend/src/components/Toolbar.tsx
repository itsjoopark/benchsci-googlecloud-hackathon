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
      <span className="toolbar-hint">
        Click node to select &middot; Double-click to expand &middot; Right-click to add to path
      </span>
    </div>
  );
}
