import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphEdge, PathNode } from "../types";
import { streamDeepThinkChat } from "../data/dataService";
import type {
  DeepThinkChatMessagePayload,
  DeepThinkConfidence,
  DeepThinkPaper,
} from "../types/api";
import "./DeepThinkPanel.css";

interface Props {
  path: PathNode[];
  edges: GraphEdge[];
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  confidence?: DeepThinkConfidence;
}

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.*?)\*\*/gs, "$1")
    .replace(/\*(.*?)\*/gs, "$1")
    .replace(/__(.*?)__/gs, "$1")
    .replace(/_(.*?)_/gs, "$1")
    .replace(/`{1,3}[^`]*`{1,3}/g, "")
    .replace(/^[-*+]\s+/gm, "• ")
    .replace(/^-{3,}$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function ConfidenceBadge({ confidence }: { confidence: DeepThinkConfidence }) {
  if (!confidence.score) return null;
  const tier = confidence.score >= 8 ? "high" : confidence.score >= 5 ? "medium" : "low";
  return (
    <span
      className={`dt-confidence dt-confidence--${tier}`}
      title={confidence.reasoning}
    >
      <span className="dt-confidence__label">Model confidence</span>
      <span className="dt-confidence__score">{confidence.score}/10</span>
    </span>
  );
}

/** Inline citation: renders a hoverable popup for a single [N] or ([N]) reference.
 *  Uses position:fixed so the popup escapes any overflow:hidden/auto ancestors.
 */
function InlineCitation({
  numbers,
  papers,
}: {
  numbers: number[];
  papers: DeepThinkPaper[];
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ bottom: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const popupRef = useRef<HTMLSpanElement>(null);

  const refs = numbers.map((n) => papers[n - 1]).filter(Boolean);
  const label = `[${numbers.join(", ")}]`;

  if (!refs.length) return <span>{label}</span>;

  const POPUP_W = 270; // approximate popup width for clamping

  const handleTriggerEnter = () => {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    // Horizontal centre, clamped to stay inside the viewport
    let left = r.left + r.width / 2;
    left = Math.min(left, window.innerWidth - POPUP_W / 2 - 8);
    left = Math.max(left, POPUP_W / 2 + 8);
    // Always show above; bottom = distance from trigger top to viewport bottom
    const bottom = window.innerHeight - r.top + 6;
    setPos({ bottom, left });
    setOpen(true);
  };

  const handleTriggerLeave = (e: React.MouseEvent) => {
    if (popupRef.current?.contains(e.relatedTarget as Node)) return;
    setOpen(false);
  };

  const handlePopupLeave = (e: React.MouseEvent) => {
    if (triggerRef.current?.contains(e.relatedTarget as Node)) return;
    setOpen(false);
  };

  return (
    <span className="dt-inline-cite">
      <span
        ref={triggerRef}
        className="dt-inline-cite__trigger"
        onMouseEnter={handleTriggerEnter}
        onMouseLeave={handleTriggerLeave}
      >
        {label}
      </span>

      {open && pos && (
        <span
          ref={popupRef}
          className="dt-inline-cite__popup"
          role="tooltip"
          style={{ bottom: pos.bottom, left: pos.left }}
          onMouseLeave={handlePopupLeave}
        >
          {refs.map((p, i) => (
            <span key={i} className="dt-inline-cite__paper">
              {p.pmid ? (
                <a
                  href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {p.title}{p.year ? ` (${p.year})` : ""}
                </a>
              ) : (
                <span>{p.title}{p.year ? ` (${p.year})` : ""}</span>
              )}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

/** Split assistant text on citation patterns and inject InlineCitation nodes. */
function renderWithCitations(
  text: string,
  papers: DeepThinkPaper[]
): React.ReactNode[] {
  // Matches ([8]), ([8, 9]), [8], [8, 9]
  const pattern = /\(\[(\d+(?:[,\s]*\d+)*)\]\)|\[(\d+(?:[,\s]*\d+)*)\]/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const numStr = (match[1] ?? match[2]).trim();
    const numbers = numStr
      .split(/[,\s]+/)
      .map(Number)
      .filter((n) => !isNaN(n) && n > 0);
    nodes.push(
      <InlineCitation key={match.index} numbers={numbers} papers={papers} />
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function MessageBubble({
  message,
  papers,
  isWelcome,
}: {
  message: ChatMessage;
  papers: DeepThinkPaper[];
  isWelcome: boolean;
}) {
  const displayText = useMemo(
    () => (message.role === "assistant" ? stripMarkdown(message.content) : message.content),
    [message.content, message.role]
  );

  // Only apply inline citation rendering for completed (non-streaming) assistant
  // responses that have papers loaded and are not the welcome message.
  const bodyContent =
    message.role === "assistant" && !message.streaming && papers.length > 0 && !isWelcome
      ? renderWithCitations(displayText, papers)
      : displayText;

  return (
    <div className={`dt-message dt-message--${message.role}`}>
      {message.role === "assistant" && (
        <span className="dt-message__avatar" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </span>
      )}
      <div className="dt-message__bubble">
        <p className="dt-message__text">
          {bodyContent}
          {message.streaming && <span className="dt-cursor" aria-hidden="true" />}
        </p>
        {message.role === "assistant" && !message.streaming && !isWelcome && (
          <div className="dt-message__footer">
            {message.confidence && message.confidence.score > 0 && (
              <ConfidenceBadge confidence={message.confidence} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DeepThinkPanel({ path, edges }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [papers, setPapers] = useState<DeepThinkPaper[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Reset chat when path changes
  const pathKey = path.map((n) => n.entityId).join("|");
  useEffect(() => {
    const names = path.map((n) => n.entityName).join(" → ");
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: `I'm ready to help you explore: ${names}. Ask me anything about how these entities are connected.`,
      },
    ]);
    setPapers([]);
    setInput("");
    abortRef.current?.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathKey]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || isStreaming) return;

    setInput("");

    const userId = `u-${Date.now()}`;
    const aiId = `a-${Date.now()}`;

    // Build history from completed messages (exclude welcome, exclude streaming)
    const history: DeepThinkChatMessagePayload[] = messages
      .filter((m) => m.id !== "welcome" && !m.streaming && m.content)
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: question },
      { id: aiId, role: "assistant", content: "", streaming: true },
    ]);

    // Build edge payloads for consecutive path pairs
    const pathEdges = [];
    for (let i = 0; i < path.length - 1; i++) {
      const srcId = path[i].entityId;
      const tgtId = path[i + 1].entityId;
      const match = edges.find(
        (e) =>
          (e.source === srcId && e.target === tgtId) ||
          (e.target === srcId && e.source === tgtId)
      );
      if (match) {
        pathEdges.push({
          source: match.source,
          target: match.target,
          predicate: match.predicate,
          evidence: (match.evidence ?? []).map((ev) => ({
            pmid: ev.pmid,
            title: ev.title,
            snippet: ev.snippet,
          })),
        });
      }
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsStreaming(true);

    try {
      await streamDeepThinkChat(
        {
          path: path.map((n) => ({
            entity_id: n.entityId,
            entity_name: n.entityName,
            entity_type: n.entityType,
            edge_predicate: n.edgePredicate,
          })),
          edges: pathEdges,
          question,
          messages: history,
        },
        {
          signal: controller.signal,
          onPapersLoaded: ({ papers: loaded }) => {
            if (loaded.length) setPapers(loaded);
          },
          onDelta: ({ text }) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiId ? { ...m, content: m.content + text } : m
              )
            );
          },
          onDone: ({ text, confidence }) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiId
                  ? { ...m, content: text || m.content, streaming: false, confidence }
                  : m
              )
            );
            setIsStreaming(false);
          },
          onError: ({ message: errMsg, partial_text }) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiId
                  ? { ...m, content: partial_text || errMsg, streaming: false }
                  : m
              )
            );
            setIsStreaming(false);
          },
        }
      );
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setIsStreaming(false);
        return;
      }
      const msg = err instanceof Error ? err.message : "Request failed.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiId ? { ...m, content: msg, streaming: false } : m
        )
      );
      setIsStreaming(false);
    }
  }, [input, isStreaming, messages, path, edges]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  return (
    <section className={`dt-panel${isOpen ? " dt-panel--open" : ""}`} aria-label="Unpack This">
      {/* Collapsible header — always visible */}
      <button
        className="dt-toggle-header"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        aria-controls="dt-chat-body"
      >
        <div className="dt-header__title-row">
          <span className="dt-header__icon" aria-hidden="true">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </span>
          <h3 className="dt-header__title">Unpack This</h3>
          <span className="dt-header__chevron" aria-hidden="true">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
            >
              <polyline points="18 15 12 9 6 15" />
            </svg>
          </span>
        </div>
        <p className="dt-header__path">{path.map((n) => n.entityName).join(" → ")}</p>
      </button>

      {/* Chat body — shown only when open */}
      {isOpen && (
        <div id="dt-chat-body" className="dt-chat-body">
          <div className="dt-messages">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                papers={papers}
                isWelcome={msg.id === "welcome"}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="dt-input-area">
            <textarea
              ref={textareaRef}
              className="dt-textarea"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about these connections… (Enter to send)"
              rows={2}
              disabled={isStreaming}
              aria-label="Ask a question about the path"
            />
            <button
              className="dt-send-btn"
              onClick={handleSend}
              disabled={isStreaming || !input.trim()}
              aria-label="Send"
            >
              {isStreaming ? (
                <span className="dt-send-spinner" />
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
