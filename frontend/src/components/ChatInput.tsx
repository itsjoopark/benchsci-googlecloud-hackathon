import { useState, useRef, useCallback } from "react";
import "./ChatInput.css";

interface Props {
  onSubmit: (query: string) => void;
  isLoading: boolean;
  onCollapse: () => void;
}

export default function ChatInput({
  onSubmit,
  isLoading,
  onCollapse,
}: Props) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
  );
}
