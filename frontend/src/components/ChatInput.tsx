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
  onCollapse: () => void;
}

export default function ChatInput({
  onSubmit,
  isLoading,
  entityFilter,
  onEntityFilterChange,
  onCollapse,
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
          <button
            className="chat-collapse-btn"
            onClick={onCollapse}
            title="Minimize search bar"
            aria-label="Minimize search bar"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
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
