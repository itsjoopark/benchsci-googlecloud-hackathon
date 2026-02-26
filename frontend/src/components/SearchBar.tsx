import { useState, useRef, useEffect, useCallback } from "react";
import type { Entity } from "../types";
import { ENTITY_COLORS } from "../types";
import "./SearchBar.css";

interface Props {
  entities: Entity[];
  onSelect: (entity: Entity) => void;
}

function entityMatchesQuery(e: Entity, lower: string): boolean {
  if (e.name.toLowerCase().includes(lower) || e.primaryId.toLowerCase().includes(lower)
    || e.id.toLowerCase().includes(lower)) return true;
  const m = e.metadata;
  if (m.symbol && String(m.symbol).toLowerCase().includes(lower)) return true;
  if (m.ncbi_gene_id && String(m.ncbi_gene_id).includes(lower)) return true;
  if (Array.isArray(m.aliases) && m.aliases.some((a: string) => a.toLowerCase().includes(lower)))
    return true;
  for (const v of Object.values(m)) {
    if (v !== undefined && v !== null && String(v).toLowerCase().includes(lower))
      return true;
  }
  return false;
}

export default function SearchBar({ entities, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback(
    (q: string) => {
      if (q.length < 2) {
        setResults([]);
        setOpen(false);
        return;
      }
      const lower = q.toLowerCase();
      const matches = entities.filter((e) => entityMatchesQuery(e, lower));
      setResults(matches);
      setOpen(matches.length > 0);
      setActiveIndex(-1);
    },
    [entities]
  );

  const handleChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(value), 300);
  };

  const handleSelect = (entity: Entity) => {
    setQuery(entity.name);
    setOpen(false);
    onSelect(entity);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(results[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (inputRef.current && !inputRef.current.parentElement?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="search-bar">
      <div className="search-input-wrapper">
        <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <input
          ref={inputRef}
          className="search-input"
          type="text"
          placeholder="Search genes, diseases, drugs, pathways..."
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => query.length >= 2 && results.length > 0 && setOpen(true)}
        />
      </div>

      {open && (
        <ul className="search-dropdown" role="listbox">
          {results.map((entity, i) => (
            <li
              key={entity.id}
              className={`search-result ${i === activeIndex ? "active" : ""}`}
              role="option"
              aria-selected={i === activeIndex}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => handleSelect(entity)}
            >
              <span
                className="type-badge"
                style={{ background: entity.color ?? ENTITY_COLORS[entity.type] }}
              >
                {entity.type}
              </span>
              <span className="result-name">{entity.name}</span>
              <span className="result-id">{entity.primaryId}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
