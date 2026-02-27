import { useState, useCallback, useRef } from "react";
import type { Entity, GraphEdge, PathNode } from "./types";
import { jsonPayloadToGraph } from "./data/adapters";
import { queryEntity, expandEntity } from "./data/dataService";
import SearchBar from "./components/SearchBar";
import EntityCard from "./components/EntityCard";
import GraphCanvas from "./components/GraphCanvas";
import EvidencePanel from "./components/EvidencePanel";
import EntityAdvancedSearchPanel from "./components/EntityAdvancedSearchPanel";
import Toolbar from "./components/Toolbar";
import ChatInput, { type EntityFilterValue } from "./components/ChatInput";
import "./App.css";

function getEntityById(entities: Entity[], nodeId: string): Entity | undefined {
  return entities.find((e) => e.id === nodeId);
}

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [path, setPath] = useState<PathNode[]>([]);
  const [graphKey, setGraphKey] = useState(0);
  const [expandedNodes, setExpandedNodes] = useState<string[]>([]);
  const [entityFilter, setEntityFilter] = useState<EntityFilterValue>("all");
  const [selectionHistory, setSelectionHistory] = useState<Entity[]>([]);
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(true);

  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [backendMessage, setBackendMessage] = useState<string | null>(null);
  const queryAbortRef = useRef<AbortController | null>(null);

  const [isExpanding, setIsExpanding] = useState(false);
  const [expandError, setExpandError] = useState<string | null>(null);
  const expandAbortRef = useRef<AbortController | null>(null);

  function mergeEntities(existing: Entity[], incoming: Entity[]): Entity[] {
    const ids = new Set(existing.map((e) => e.id));
    return [...existing, ...incoming.filter((e) => !ids.has(e.id))];
  }

  function mergeEdges(
    existing: GraphEdge[],
    incoming: GraphEdge[]
  ): GraphEdge[] {
    const ids = new Set(existing.map((e) => e.id));
    return [...existing, ...incoming.filter((e) => !ids.has(e.id))];
  }

  const addToSelectionHistory = useCallback((entity: Entity) => {
    setSelectionHistory((prev) => {
      const filtered = prev.filter((e) => e.id !== entity.id);
      return [entity, ...filtered];
    });
  }, []);

  const handleQuery = useCallback(
    async (query: string) => {
      // Cancel any in-flight request
      queryAbortRef.current?.abort();
      const controller = new AbortController();
      queryAbortRef.current = controller;

      setIsQuerying(true);
      setQueryError(null);
      setBackendMessage(null);

      try {
        const payload = await queryEntity(query, controller.signal);

        // Backend "not found" message
        if (payload.message) {
          setBackendMessage(payload.message);
          return;
        }

        // Empty results
        if (!payload.nodes || payload.nodes.length === 0) {
          setBackendMessage(`No results found for "${query}".`);
          return;
        }

        const { entities: e, edges: ed } = jsonPayloadToGraph(payload);

        // Limit initial connections to 5 neighbors around the seed node
        const MAX_INITIAL_NODES = 5;
        const centerId = payload.center_node_id;
        const seedNode = e.find((ent) => ent.id === centerId);
        const neighbors = e.filter((ent) => ent.id !== centerId);

        let keptNeighbors: typeof neighbors;
        if (neighbors.length <= MAX_INITIAL_NODES) {
          keptNeighbors = neighbors;
        } else {
          const scoreMap = new Map<string, number>();
          for (const edge of ed) {
            const s = edge.score ?? 0;
            for (const id of [edge.source, edge.target]) {
              scoreMap.set(id, Math.max(scoreMap.get(id) ?? 0, s));
            }
          }
          neighbors.sort(
            (a, b) => (scoreMap.get(b.id) ?? 0) - (scoreMap.get(a.id) ?? 0)
          );
          keptNeighbors = neighbors.slice(0, MAX_INITIAL_NODES);
        }

        const finalEntities = seedNode
          ? [seedNode, ...keptNeighbors]
          : keptNeighbors;
        const keptIds = new Set(finalEntities.map((ent) => ent.id));
        const finalEdges = ed.filter(
          (edge) => keptIds.has(edge.source) && keptIds.has(edge.target)
        );

        setEntities(finalEntities);
        setEdges(finalEdges);
        setSelectedEdge(null);
        setPath([]);
        setExpandedNodes(centerId ? [centerId] : []);

        // Auto-select the center node
        const center = e.find((ent) => ent.id === payload.center_node_id);
        if (center) {
          setSelectedEntity(center);
          addToSelectionHistory(center);
        } else {
          setSelectedEntity(null);
        }

        setGraphKey((k) => k + 1);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") return;
        setQueryError(
          err instanceof Error ? err.message : "An unexpected error occurred."
        );
      } finally {
        setIsQuerying(false);
      }
    },
    [addToSelectionHistory]
  );

  const handleSearchSelect = useCallback(
    (entity: Entity) => {
      setSelectedEntity(entity);
      setSelectedEdge(null);
      setPath([]);
      setExpandedNodes([]);
      addToSelectionHistory(entity);
      setSidebarOpen(true);
      setRightSidebarCollapsed(false);
      setGraphKey((k) => k + 1);
    },
    [addToSelectionHistory]
  );

  const handleNodeSelect = useCallback(
    (nodeId: string) => {
      // Toggle: clicking the already-selected node deselects it
      if (selectedEntity?.id === nodeId) {
        setSelectedEntity(null);
        setSelectedEdge(null);
        return;
      }
      const entity = getEntityById(entities, nodeId);
      if (entity) {
        setSelectedEntity(entity);
        setSelectedEdge(null);
        addToSelectionHistory(entity);
        setSidebarOpen(true);
        setRightSidebarCollapsed(false);
      }
    },
    [entities, addToSelectionHistory, selectedEntity]
  );

  const handleNodeExpand = useCallback(
    async (nodeId: string) => {
      if (expandedNodes.includes(nodeId) || isExpanding) return;

      expandAbortRef.current?.abort();
      const controller = new AbortController();
      expandAbortRef.current = controller;

      setExpandedNodes((prev) => [...prev, nodeId]);
      setIsExpanding(true);
      setExpandError(null);

      try {
        const payload = await expandEntity(nodeId, controller.signal);

        if (payload.message || !payload.nodes?.length) {
          if (payload.message) setExpandError(payload.message);
          return;
        }

        const { entities: newE, edges: newEd } = jsonPayloadToGraph(payload);

        // Cap expansion to 5 truly new nodes, ranked by edge confidence
        const MAX_EXPANSION_NODES = 5;
        const existingIds = new Set(entities.map((e) => e.id));
        const trulyNew = newE.filter((e) => !existingIds.has(e.id));

        let keptNew: typeof trulyNew;
        if (trulyNew.length <= MAX_EXPANSION_NODES) {
          keptNew = trulyNew;
        } else {
          const scoreMap = new Map<string, number>();
          for (const edge of newEd) {
            const s = edge.score ?? 0;
            for (const id of [edge.source, edge.target]) {
              scoreMap.set(id, Math.max(scoreMap.get(id) ?? 0, s));
            }
          }
          trulyNew.sort(
            (a, b) => (scoreMap.get(b.id) ?? 0) - (scoreMap.get(a.id) ?? 0)
          );
          keptNew = trulyNew.slice(0, MAX_EXPANSION_NODES);
        }

        const alreadyExisting = newE.filter((e) => existingIds.has(e.id));
        const finalEntities = [...alreadyExisting, ...keptNew];
        const finalNodeIds = new Set([
          ...existingIds,
          ...finalEntities.map((e) => e.id),
        ]);
        const finalEdges = newEd.filter(
          (e) => finalNodeIds.has(e.source) && finalNodeIds.has(e.target)
        );

        setEntities((prev) => mergeEntities(prev, finalEntities));
        setEdges((prev) => mergeEdges(prev, finalEdges));
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        setExpandError(
          err instanceof Error ? err.message : "Failed to expand node."
        );
        setExpandedNodes((prev) => prev.filter((id) => id !== nodeId));
      } finally {
        setIsExpanding(false);
      }
    },
    [expandedNodes, isExpanding, entities]
  );

  const handleEdgeSelect = useCallback(
    (edgeId: string) => {
      const edge = edges.find((e) => e.id === edgeId);
      if (edge) {
        setSelectedEdge(edge);
      }
    },
    [edges]
  );

  const handleAddToPath = useCallback(
    (nodeId: string) => {
      const entity = getEntityById(entities, nodeId);
      if (!entity) return;

      const connEdge =
        path.length > 0
          ? edges.find(
              (e) =>
                (e.source === path[path.length - 1].entityId &&
                  e.target === nodeId) ||
                (e.target === path[path.length - 1].entityId &&
                  e.source === nodeId)
            )
          : undefined;

      setPath((prev) => [
        ...prev,
        {
          entityId: entity.id,
          entityName: entity.name,
          entityType: entity.type,
          edgePredicate: connEdge?.label ?? connEdge?.predicate,
        },
      ]);
    },
    [path, edges, entities]
  );

  const handleFit = useCallback(() => setGraphKey((k) => k + 1), []);

  const graphLoaded = entities.length > 0;

  const evidence = selectedEdge?.evidence ?? [];

  const filteredEntities =
    entityFilter === "all" ||
    (Array.isArray(entityFilter) && entityFilter.length === 0)
      ? entities
      : entities.filter((e) => entityFilter.includes(e.type));
  const filteredEntityIds = new Set(filteredEntities.map((e) => e.id));
  const filteredEdges =
    entityFilter === "all"
      ? edges
      : edges.filter(
          (e) => filteredEntityIds.has(e.source) && filteredEntityIds.has(e.target)
        );

  return (
    <div className="app-wrapper">
      <nav className="top-nav">
        <h1 className="top-nav-title">BioRender</h1>
      </nav>
      <div className="app-layout">
      {/* Left Pane - Path History */}
      <aside className={`pane pane-left ${sidebarOpen ? "" : "collapsed"}`}>
        <div className="pane-header">
          <h2 className="path-history-title">Path History</h2>
        </div>
        <SearchBar entities={entities} onSelect={handleSearchSelect} />
        <div className="path-history-list">
          {selectionHistory.map((entity) => (
            <EntityCard key={entity.id} entity={entity} />
          ))}
          {selectionHistory.length > 0 && (
            <button
              className="path-history-clear"
              onClick={() => setSelectionHistory([])}
            >
              Clear history
            </button>
          )}
        </div>
      </aside>

      {/* Centre Pane */}
      <main className="pane pane-centre">
        {/* Sidebar toggle */}
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {sidebarOpen ? (
              <>
                <path d="M15 18l-6-6 6-6" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </button>

        <Toolbar onFit={handleFit} disabled={!graphLoaded} pathLength={path.length} onClearPath={() => setPath([])} />

        {/* Error banner */}
        {queryError && (
          <div className="query-error-banner">
            <span>{queryError}</span>
            <button onClick={() => setQueryError(null)} aria-label="Dismiss error">&times;</button>
          </div>
        )}

        {/* Backend message banner */}
        {backendMessage && (
          <div className="query-message-banner">
            <span>{backendMessage}</span>
            <button onClick={() => setBackendMessage(null)} aria-label="Dismiss message">&times;</button>
          </div>
        )}

        {/* Expand error banner */}
        {expandError && (
          <div className="expand-error-banner">
            <span>{expandError}</span>
            <button onClick={() => setExpandError(null)} aria-label="Dismiss error">&times;</button>
          </div>
        )}

        {/* Expand loading indicator */}
        {isExpanding && (
          <div className="expand-loading-indicator">
            <div className="expand-loading-spinner" />
            <span>Expanding...</span>
          </div>
        )}

        {/* Loading overlay */}
        {isQuerying && (
          <div className="query-loading-overlay">
            <div className="query-loading-spinner" />
          </div>
        )}

        {/* Empty state */}
        {!graphLoaded && !isQuerying && !queryError && !backendMessage && (
          <div className="empty-state">
            <p>Enter a gene, disease, drug, pathway, or protein to explore its knowledge graph.</p>
          </div>
        )}

        <GraphCanvas
          key={`${graphKey}-${entityFilter === "all" ? "all" : [...entityFilter].sort().join(",")}`}
          entities={filteredEntities}
          edges={filteredEdges}
          selectedEntityId={
            selectedEntity && filteredEntityIds.has(selectedEntity.id)
              ? selectedEntity.id
              : null
          }
          selectedEdgeId={selectedEdge?.id ?? null}
          expandedNodes={expandedNodes}
          path={path}
          onNodeSelect={handleNodeSelect}
          onNodeExpand={handleNodeExpand}
          onEdgeSelect={handleEdgeSelect}
          onAddToPath={handleAddToPath}
        />

        {/* Chat input */}
        {chatExpanded ? (
          <ChatInput
            onSubmit={handleQuery}
            isLoading={isQuerying}
            entityFilter={entityFilter}
            onEntityFilterChange={setEntityFilter}
            onCollapse={() => setChatExpanded(false)}
          />
        ) : (
          <button
            className="chat-expand-fab"
            onClick={() => setChatExpanded(true)}
            aria-label="Open search"
            title="Open search"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
        )}
      </main>

      {/* Right Pane */}
      {(selectedEdge || selectedEntity) && (
        <aside
          className={`pane pane-right ${rightSidebarCollapsed ? "collapsed" : ""}`}
        >
          {rightSidebarCollapsed ? (
            <button
              className="right-pane-expand"
              onClick={() => setRightSidebarCollapsed(false)}
              aria-label="Expand sidebar"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
          ) : selectedEdge ? (
            <EvidencePanel
              edge={selectedEdge}
              evidence={evidence}
              entities={entities}
              onClose={() => setSelectedEdge(null)}
              onCollapse={() => setRightSidebarCollapsed(true)}
            />
          ) : selectedEntity ? (
            <EntityAdvancedSearchPanel
              entity={selectedEntity}
              edges={edges}
              onCollapse={() => setRightSidebarCollapsed(true)}
            />
          ) : null}
        </aside>
      )}
      </div>
    </div>
  );
}

export default App;
