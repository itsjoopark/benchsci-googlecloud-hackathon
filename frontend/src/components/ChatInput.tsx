import { useState, useRef, useCallback, useEffect } from "react";
import type { EntityType } from "../types";
import "./ChatInput.css";

export type EntityFilterValue = EntityType[] | "all";

const ENTITY_TYPE_OPTIONS: { value: EntityType; label: string }[] = [
  { value: "gene", label: "Gene" },
  { value: "disease", label: "Disease" },
  { value: "drug", label: "Drug" },
  { value: "pathway", label: "Pathway" },
  { value: "protein", label: "Protein" },
];

interface Props {
  onSubmit: (query: string) => void;
  isLoading: boolean;
  entityFilter: EntityFilterValue;
  onEntityFilterChange: (filter: EntityFilterValue) => void;
}

export default function ChatInput({
  onSubmit,
  isLoading,
  entityFilter,
  onEntityFilterChange,
}: Props) {
  const [value, setValue] = useState("");
  const [entityDropdownOpen, setEntityDropdownOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setEntityDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
    setValue("");
  }, [value, onSubmit, isLoading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isAllSelected = entityFilter === "all";
  const selectedTypes = isAllSelected ? [] : entityFilter;

  const entityButtonLabel =
    isAllSelected ? "Entity" : selectedTypes.map((t) => ENTITY_TYPE_OPTIONS.find((o) => o.value === t)?.label ?? t).join(", ");

  const handleAllClick = () => {
    onEntityFilterChange("all");
    setEntityDropdownOpen(false);
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
    <div className="chat-input-wrapper">
      <div className="chat-input-container">
        <textarea
          ref={inputRef}
          className="chat-textarea"
          placeholder="Search for a gene, disease, drug, pathway, or protein..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={isLoading}
        />
        <div className="chat-actions">
          <div className="chat-actions-left">
            <button className="chat-action-btn" title="Attach" disabled>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <button className="chat-action-btn chat-tools-btn" disabled>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              <span>Tools</span>
            </button>
          </div>
          <div className="chat-actions-right">
            <div className="chat-entity-dropdown" ref={dropdownRef}>
              <button
                type="button"
                className="chat-entity-btn"
                onClick={() => setEntityDropdownOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={entityDropdownOpen}
              >
                <span className="chat-entity-btn-label">{entityButtonLabel}</span>
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className={entityDropdownOpen ? "chat-entity-chevron open" : "chat-entity-chevron"}
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              {entityDropdownOpen && (
                <ul
                  className="chat-entity-menu"
                  role="group"
                  aria-label="Filter by entity type"
                >
                  <li>
                    <button
                      type="button"
                      className={`chat-entity-option ${isAllSelected ? "selected" : ""}`}
                      role="menuitemcheckbox"
                      aria-checked={isAllSelected}
                      onClick={handleAllClick}
                    >
                      <span className="chat-entity-check">{isAllSelected ? "✓" : ""}</span>
                      All
                    </button>
                  </li>
                  {ENTITY_TYPE_OPTIONS.map((opt) => {
                    const isSelected = !isAllSelected && selectedTypes.includes(opt.value);
                    return (
                      <li key={opt.value}>
                        <button
                          type="button"
                          className={`chat-entity-option ${isSelected ? "selected" : ""}`}
                          role="menuitemcheckbox"
                          aria-checked={isSelected}
                          onClick={() => handleTypeToggle(opt.value)}
                        >
                          <span className="chat-entity-check">{isSelected ? "✓" : ""}</span>
                          {opt.label}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <button
              className="chat-submit-btn"
              onClick={handleSubmit}
              disabled={!value.trim() || isLoading}
              aria-label="Send"
            >
              {isLoading ? (
                <span className="chat-submit-spinner" />
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
