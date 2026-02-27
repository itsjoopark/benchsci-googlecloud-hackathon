import { useState, useRef, useEffect } from "react";
import { ENTITY_COLORS } from "../types";
import type { EntityType, EntityFilterValue } from "../types";
import "./EntityFilter.css";

const ENTITY_TYPE_OPTIONS: { value: EntityType; label: string }[] = [
  { value: "gene", label: "Gene" },
  { value: "disease", label: "Disease" },
  { value: "drug", label: "Drug" },
];

interface Props {
  entityFilter: EntityFilterValue;
  onEntityFilterChange: (filter: EntityFilterValue) => void;
}

export default function EntityFilter({ entityFilter, onEntityFilterChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const isAllSelected = entityFilter === "all";
  const selectedTypes = isAllSelected ? [] : entityFilter;

  const activeCount = isAllSelected ? ENTITY_TYPE_OPTIONS.length : selectedTypes.length;

  const handleAllClick = () => {
    onEntityFilterChange("all");
    setOpen(false);
  };

  const handleTypeToggle = (type: EntityType) => {
    if (isAllSelected) {
      onEntityFilterChange([type]);
    } else {
      const next = selectedTypes.includes(type)
        ? selectedTypes.filter((t) => t !== type)
        : [...selectedTypes, type];
      onEntityFilterChange(next.length === 0 ? "all" : next);
    }
  };

  return (
    <div className="entity-filter" ref={ref}>
      <button
        type="button"
        className="entity-filter-btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        <span className="entity-filter-label">Filter ({activeCount})</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={open ? "entity-filter-chevron open" : "entity-filter-chevron"}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <ul className="entity-filter-menu" role="group" aria-label="Filter by entity type">
          <li>
            <button
              type="button"
              className={`entity-filter-option entity-filter-option-all ${isAllSelected ? "selected" : ""}`}
              role="menuitemcheckbox"
              aria-checked={isAllSelected}
              onClick={handleAllClick}
            >
              <span className="entity-filter-indicator entity-filter-check">
                {isAllSelected ? "✓" : ""}
              </span>
              All types
            </button>
          </li>
          {ENTITY_TYPE_OPTIONS.map((opt) => {
            const isSelected = !isAllSelected && selectedTypes.includes(opt.value);
            return (
              <li key={opt.value}>
                <button
                  type="button"
                  className={`entity-filter-option ${isSelected ? "selected" : ""}`}
                  role="menuitemcheckbox"
                  aria-checked={isSelected}
                  onClick={() => handleTypeToggle(opt.value)}
                >
                  <span className="entity-filter-indicator" aria-hidden="true">
                    <svg className="entity-filter-dot-icon" viewBox="0 0 8 8" width="8" height="8">
                      <circle cx="4" cy="4" r="4" fill={ENTITY_COLORS[opt.value]} />
                    </svg>
                  </span>
                  <span
                    className="entity-filter-option-label"
                  >
                    {opt.label}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
