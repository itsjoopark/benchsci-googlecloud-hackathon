import { useState, useCallback, useEffect } from "react";
import type { Entity, GraphEdge, PathNode } from "./types";
import { jsonPayloadToGraph } from "./data/adapters";
import { fetchGraph } from "./data/dataService";
import type { JsonGraphPayload } from "./types/api";
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
  const [graphPayload, setGraphPayload] = useState<JsonGraphPayload | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [path, setPath] = useState<PathNode[]>([]);
  const [graphKey, setGraphKey] = useState(0);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [entityFilter, setEntityFilter] = useState<EntityFilterValue>("all");
  const [selectionHistory, setSelectionHistory] = useState<Entity[]>([]);
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false);

  const addToSelectionHistory = useCallback((entity: Entity) => {
    setSelectionHistory((prev) => {
      const filtered = prev.filter((e) => e.id !== entity.id);
      return [entity, ...filtered];
    });
  }, []);

  useEffect(() => {
    fetchGraph()
      .then(setGraphPayload)
      .catch((err) => console.error("Failed to load graph:", err));
  }, []);

  const handleSearchSelect = useCallback(
    (entity: Entity) => {
      if (!graphPayload) return;
      const { entities: e, edges: ed } = jsonPayloadToGraph(graphPayload);
      setEntities(e);
      setEdges(ed);
      setSelectedEntity(entity);
      setSelectedEdge(null);
      setPath([]);
      setExpandedNodes(new Set());
      addToSelectionHistory(entity);
      setSidebarOpen(true);
      setRightSidebarCollapsed(false);
      setGraphKey((k) => k + 1);
    },
    [graphPayload, addToSelectionHistory]
  );

  const handleNodeSelect = useCallback(
    (nodeId: string) => {
      // Toggle: clicking the already-selected node deselects it
      if (selectedEntity?.id === nodeId) {
        setSelectedEntity(null);
        setSelectedEdge(null);
        return;
      }
      const entity =
        getEntityById(entities, nodeId) ??
        (graphPayload &&
          jsonPayloadToGraph(graphPayload).entities.find((e) => e.id === nodeId));
      if (entity) {
        setSelectedEntity(entity);
        setSelectedEdge(null);
        addToSelectionHistory(entity);
        setSidebarOpen(true);
        setRightSidebarCollapsed(false);
      }
    },
    [entities, graphPayload, addToSelectionHistory, selectedEntity]
  );

  const handleNodeExpand = useCallback((nodeId: string) => {
    setExpandedNodes((prev) => new Set(prev).add(nodeId));
  }, []);

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

  const searchEntities = graphPayload
    ? jsonPayloadToGraph(graphPayload).entities
    : [];

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
        <SearchBar entities={searchEntities} onSelect={handleSearchSelect} />
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

        <Toolbar onFit={handleFit} disabled={!graphLoaded} />
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
        <ChatInput
          graphPayload={graphPayload}
          onSubmit={handleSearchSelect}
          entityFilter={entityFilter}
          onEntityFilterChange={setEntityFilter}
        />
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
