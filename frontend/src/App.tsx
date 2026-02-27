import { useState, useCallback, useRef, useMemo, useEffect } from "react";
import type { Entity, GraphEdge, EntityFilterValue } from "./types";
import { jsonPayloadToGraph } from "./data/adapters";
import { queryEntity, expandEntity } from "./data/dataService";
import { saveSnapshot, loadSnapshot } from "./data/snapshotService";
import type { GraphSnapshot } from "./data/snapshotService";
import { getSnapshotIdFromUrl, setSnapshotIdInUrl } from "./utils/urlState";
import { rankCandidates } from "./utils/rankCandidates";
import type { OverviewStreamRequestPayload } from "./types/api";
import PathBreadcrumb from "./components/PathBreadcrumb";
import GraphCanvas from "./components/GraphCanvas";
import EvidencePanel from "./components/EvidencePanel";
import EntityAdvancedSearchPanel from "./components/EntityAdvancedSearchPanel";
import AIOverviewCard from "./components/AIOverviewCard";
import DeepThinkPanel from "./components/DeepThinkPanel";
import Toolbar from "./components/Toolbar";
import ChatInput from "./components/ChatInput";
import GraphLegend from "./components/GraphLegend";
import EntityFilter from "./components/EntityFilter";
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
  const [graphKey, setGraphKey] = useState(0);
  const [fitRequest, setFitRequest] = useState(0);
  const [expandedNodes, setExpandedNodes] = useState<string[]>([]);
  const [entityFilter, setEntityFilter] = useState<EntityFilterValue>("all");
  const [selectionHistory, setSelectionHistory] = useState<Entity[]>([]);
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(true);
  const [overviewRatio, setOverviewRatio] = useState(0.40);
  const leftPaneBodyRef = useRef<HTMLDivElement>(null);
  const [activeRightSection, setActiveRightSection] = useState<'overview' | 'search' | 'deepthink'>('overview');

  // Maps an entity ID that was expanded → the entity/edge IDs that were newly added
  const [expansionSnapshots, setExpansionSnapshots] = useState<
    Map<string, { entityIds: string[]; edgeIds: string[] }>
  >(new Map());

  const [centerNodeId, setCenterNodeId] = useState("");
  const [overviewHistory, setOverviewHistory] = useState<
    { selectionKey: string; selectionType: "edge" | "node"; summary: string }[]
  >([]);

  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [backendMessage, setBackendMessage] = useState<string | null>(null);
  const queryAbortRef = useRef<AbortController | null>(null);

  const [isExpanding, setIsExpanding] = useState(false);
  const [expandError, setExpandError] = useState<string | null>(null);
  const expandAbortRef = useRef<AbortController | null>(null);

  // Ordered node IDs when displaying a shortest-path result
  const [pathNodeIds, setPathNodeIds] = useState<string[]>([]);

  // Current search query (for snapshot saving)
  const [currentQuery, setCurrentQuery] = useState("");
  // Latest node positions from GraphCanvas (for snapshot saving)
  const graphPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  // Whether a snapshot is currently being saved
  const [isSavingSnapshot, setIsSavingSnapshot] = useState(false);
  // Brief toast message for share confirmation
  const [shareToast, setShareToast] = useState<string | null>(null);

  // Snapshot of the initial query result so Reset can restore it
  const initialGraphStateRef = useRef<{ entities: Entity[]; edges: GraphEdge[]; centerNodeId: string; pathNodeIds?: string[] } | null>(null);

  /** Merge incoming entities from an expand response. New entities are added;
   * existing entities that appear in the response are updated with the
   * incoming size (and optional fields) so node sizes reflect co-occurrence
   * relative to the newly expanded/clicked node. */
  function mergeEntities(existing: Entity[], incoming: Entity[]): Entity[] {
    const byId = new Map<string, Entity>(existing.map((e) => [e.id, e]));
    for (const e of incoming) {
      const current = byId.get(e.id);
      if (!current) {
        byId.set(e.id, e);
      } else {
        byId.set(e.id, {
          ...current,
          size: e.size ?? current.size,
        });
      }
    }
    return Array.from(byId.values());
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

      setCurrentQuery(query);
      setIsQuerying(true);
      setQueryError(null);
      setBackendMessage(null);
      setPathNodeIds([]);

      try {
        const payload = await queryEntity(query, controller.signal);

        // Backend "not found" message
        if (payload.message) {
          setBackendMessage(payload.message);
          setCenterNodeId("");
          return;
        }

        // Empty results
        if (!payload.nodes || payload.nodes.length === 0) {
          setBackendMessage(`No results found for "${query}".`);
          setCenterNodeId("");
          return;
        }

        const { entities: e, edges: ed } = jsonPayloadToGraph(payload);

        // === PATH MODE: shortest path response ===
        if (payload.path_node_ids && payload.path_node_ids.length > 0) {
          const pathIds = payload.path_node_ids;

          // Show ALL nodes on the path (no neighbor limiting)
          initialGraphStateRef.current = {
            entities: e,
            edges: ed,
            centerNodeId: payload.center_node_id ?? "",
            pathNodeIds: pathIds,
          };

          setEntities(e);
          setEdges(ed);
          setSelectedEdge(null);
          // Mark all path nodes EXCEPT the last as expanded,
          // so the user can double-click the last node to expand
          setExpandedNodes(pathIds.slice(0, -1));
          setExpansionSnapshots(new Map());
          setCenterNodeId(payload.center_node_id ?? "");
          setPathNodeIds(pathIds);
          setOverviewHistory([]);

          // Build selection history in path order (newest-first for PathBreadcrumb)
          const pathOrderedEntities = pathIds
            .map((id) => e.find((ent) => ent.id === id))
            .filter((ent): ent is Entity => !!ent);
          setSelectionHistory([...pathOrderedEntities].reverse());

          // Select the first path entity (the starting point) for AI overview
          const startEntity = e.find((ent) => ent.id === pathIds[0]);
          if (startEntity) {
            setSelectedEntity(startEntity);
          }

          // Open both sidebars so exploration path + AI overview are visible
          setSidebarOpen(true);
          setRightSidebarCollapsed(false);

          setGraphKey((k) => k + 1);
          setChatExpanded(false);
          return;
        }

        // === SEARCH MODE: existing single-entity flow ===
        setPathNodeIds([]);

        // Limit initial connections to 5 neighbors around the seed node
        const MAX_INITIAL_NODES = 5;
        const centerId = payload.center_node_id;
        const seedNode = e.find((ent) => ent.id === centerId);
        const neighbors = e.filter((ent) => ent.id !== centerId);

        const keptNeighbors = rankCandidates({
          candidates: neighbors,
          edges: ed,
          existingEntities: seedNode ? [seedNode] : [],
          maxResults: MAX_INITIAL_NODES,
        });

        const finalEntities = seedNode
          ? [seedNode, ...keptNeighbors]
          : keptNeighbors;
        const keptIds = new Set(finalEntities.map((ent) => ent.id));
        const finalEdges = ed.filter(
          (edge) => keptIds.has(edge.source) && keptIds.has(edge.target)
        );

        // Cache for reset
        initialGraphStateRef.current = { entities: finalEntities, edges: finalEdges, centerNodeId: payload.center_node_id ?? "" };

        setEntities(finalEntities);
        setEdges(finalEdges);
        setSelectedEdge(null);
        setExpandedNodes(centerId ? [centerId] : []);
        setExpansionSnapshots(new Map());
        setCenterNodeId(payload.center_node_id ?? "");
        setOverviewHistory([]);

        // Auto-select the center node
        const center = e.find((ent) => ent.id === payload.center_node_id);
        if (center) {
          setSelectedEntity(center);
          addToSelectionHistory(center);
        } else {
          setSelectedEntity(null);
        }

        setGraphKey((k) => k + 1);
        setTimeout(() => setFitRequest((n) => n + 1), 600);
        setChatExpanded(false);
        setSidebarOpen(true);
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

  // Focus-based blur: only the selected node, its direct neighbors, and path nodes are fully visible
  const disabledNodeIds = useMemo(() => {
    if (entities.length === 0 || !selectedEntity) return new Set<string>();
    const focusId = selectedEntity.id;
    const activeNodeIds = new Set<string>([focusId]);
    for (const edge of edges) {
      if (edge.source === focusId) activeNodeIds.add(edge.target);
      if (edge.target === focusId) activeNodeIds.add(edge.source);
    }
    // Nodes on the navigation path are always active
    for (const id of pathNodeIds) {
      activeNodeIds.add(id);
    }
    const disabled = new Set<string>();
    for (const entity of entities) {
      if (!activeNodeIds.has(entity.id)) disabled.add(entity.id);
    }
    return disabled;
  }, [entities, edges, selectedEntity, pathNodeIds]);

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
        setSidebarOpen(true);
        setRightSidebarCollapsed(false);
        addToSelectionHistory(entity);
      }
    },
    [entities, selectedEntity, disabledNodeIds, addToSelectionHistory]
  );

  const handleNodeExpand = useCallback(
    async (nodeId: string) => {
      if (disabledNodeIds.has(nodeId)) return;
      if (expandedNodes.includes(nodeId) || isExpanding) return;

      // Also add to selection history on double-click expand
      const entity = getEntityById(entities, nodeId);
      if (entity) {
        setSelectedEntity(entity);
        addToSelectionHistory(entity);
        setSidebarOpen(true);
        setRightSidebarCollapsed(false);
      }

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

        const keptNew = rankCandidates({
          candidates: trulyNew,
          edges: newEd,
          existingEntities: entities,
          maxResults: MAX_EXPANSION_NODES,
        });

        const alreadyExisting = newE.filter((e) => existingIds.has(e.id));
        const finalEntities = [...alreadyExisting, ...keptNew];
        const finalNodeIds = new Set([
          ...existingIds,
          ...finalEntities.map((e) => e.id),
        ]);
        const finalEdges = newEd.filter(
          (e) => finalNodeIds.has(e.source) && finalNodeIds.has(e.target)
        );

        // Track newly added IDs for pruning
        const newEntityIds = keptNew.map((e) => e.id);
        const existingEdgeIds = new Set(edges.map((e) => e.id));
        const newEdgeIds = finalEdges
          .filter((e) => !existingEdgeIds.has(e.id))
          .map((e) => e.id);
        setExpansionSnapshots((snapshots) => {
          const next = new Map(snapshots);
          next.set(nodeId, { entityIds: newEntityIds, edgeIds: newEdgeIds });
          return next;
        });

        setEntities((prev) => mergeEntities(prev, finalEntities));
        setEdges((prev) => mergeEdges(prev, finalEdges));
        setTimeout(() => setFitRequest((n) => n + 1), 600);
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
    [expandedNodes, isExpanding, entities, addToSelectionHistory, edges, disabledNodeIds]
  );

  const handlePruneHistory = useCallback(
    (pruneIndex: number) => {
      // selectionHistory is newest-first; pruneIndex and everything above (0..pruneIndex)
      // is removed. Everything from pruneIndex+1 onward is kept.
      setSelectionHistory((prev) => {
        const removed = prev.slice(0, pruneIndex + 1);
        const kept = prev.slice(pruneIndex + 1);

        // Collect entity/edge IDs introduced by expansions of removed history entries
        const idsToRemove = new Set<string>();
        const edgeIdsToRemove = new Set<string>();
        for (const removedEntity of removed) {
          const snap = expansionSnapshots.get(removedEntity.id);
          if (snap) {
            snap.entityIds.forEach((id) => idsToRemove.add(id));
            snap.edgeIds.forEach((id) => edgeIdsToRemove.add(id));
          }
        }

        // Also remove the expanded-node markers
        const removedIds = new Set(removed.map((e) => e.id));
        setExpandedNodes((prev) => prev.filter((id) => !removedIds.has(id)));

        // If the history becomes empty, wipe the entire graph
        if (kept.length === 0) {
          setEntities([]);
          setEdges([]);
          setExpandedNodes([]);
          setExpansionSnapshots(new Map());
          setSelectedEntity(null);
          setSelectedEdge(null);
          setGraphKey((k) => k + 1);
          return kept;
        }

        // Prune entities and edges from the graph
        if (idsToRemove.size > 0 || edgeIdsToRemove.size > 0) {
          setEntities((prev) => prev.filter((e) => !idsToRemove.has(e.id)));
          setEdges((prev) =>
            prev.filter(
              (e) =>
                !edgeIdsToRemove.has(e.id) &&
                !idsToRemove.has(e.source) &&
                !idsToRemove.has(e.target)
            )
          );
        }

        // Clean up snapshots for removed entries
        setExpansionSnapshots((snapshots) => {
          const next = new Map(snapshots);
          removedIds.forEach((id) => next.delete(id));
          return next;
        });

        // Clear selected entity/edge if they're being pruned
        setSelectedEntity((sel) =>
          sel && (removedIds.has(sel.id) || idsToRemove.has(sel.id)) ? null : sel
        );
        setSelectedEdge((sel) =>
          sel &&
          (edgeIdsToRemove.has(sel.id) ||
            idsToRemove.has(sel.source) ||
            idsToRemove.has(sel.target))
            ? null
            : sel
        );

        return kept;
      });
    },
    [expansionSnapshots]
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

  const handleDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const body = leftPaneBodyRef.current;
    if (!body) return;
    const PATH_MIN_PX = 60;
    const OVERVIEW_MIN_PX = 120;
    const HANDLE_PX = 6;
    const onMouseMove = (ev: MouseEvent) => {
      const rect = body.getBoundingClientRect();
      const minPx = PATH_MIN_PX;
      const maxPx = rect.height - OVERVIEW_MIN_PX - HANDLE_PX;
      const clampedPx = Math.max(minPx, Math.min(maxPx, ev.clientY - rect.top));
      setOverviewRatio(clampedPx / rect.height);
    };
    const onMouseUp = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, []);

  const handleFit = useCallback(() => setFitRequest((n) => n + 1), []);

  const handleResetExploration = useCallback(() => {
    const snapshot = initialGraphStateRef.current;
    if (!snapshot) return;
    expandAbortRef.current?.abort();
    setIsExpanding(false);
    setEntities(snapshot.entities);
    setEdges(snapshot.edges);
    setCenterNodeId(snapshot.centerNodeId);
    setExpansionSnapshots(new Map());
    setSelectedEdge(null);
    setOverviewHistory([]);

    const savedPathIds = snapshot.pathNodeIds ?? [];
    setPathNodeIds(savedPathIds);

    if (savedPathIds.length > 0) {
      // Restore path mode: expand all except last, rebuild path selection history
      setExpandedNodes(savedPathIds.slice(0, -1));
      const pathOrderedEntities = savedPathIds
        .map((id) => snapshot.entities.find((e) => e.id === id))
        .filter((ent): ent is Entity => !!ent);
      setSelectionHistory([...pathOrderedEntities].reverse());
      const startEntity = snapshot.entities.find((e) => e.id === savedPathIds[0]);
      if (startEntity) { setSelectedEntity(startEntity); }
      else { setSelectedEntity(null); }
    } else {
      // Restore search mode
      setExpandedNodes(snapshot.centerNodeId ? [snapshot.centerNodeId] : []);
      setSelectionHistory([]);
      const center = snapshot.entities.find((e) => e.id === snapshot.centerNodeId);
      if (center) { setSelectedEntity(center); addToSelectionHistory(center); }
      else { setSelectedEntity(null); }
    }

    setGraphKey((k) => k + 1);
  }, [addToSelectionHistory]);

  // Receive live node positions from GraphCanvas
  const handlePositionsUpdate = useCallback((positions: Map<string, { x: number; y: number }>) => {
    graphPositionsRef.current = positions;
  }, []);

  // Save current graph state as a shareable snapshot
  const handleSaveSnapshot = useCallback(async () => {
    if (isSavingSnapshot || entities.length === 0) return;
    setIsSavingSnapshot(true);
    try {
      const nodePositions: Record<string, { x: number; y: number }> = {};
      graphPositionsRef.current.forEach((pos, id) => {
        nodePositions[id] = { x: pos.x, y: pos.y };
      });

      const snapshot: GraphSnapshot = {
        query: currentQuery,
        entities,
        edges,
        expanded_nodes: expandedNodes,
        center_node_id: centerNodeId,
        path_node_ids: pathNodeIds,
        entity_filter: entityFilter,
        node_positions: nodePositions,
        selection_history: selectionHistory,
        selected_entity_id: selectedEntity?.id ?? null,
      };

      const id = await saveSnapshot(snapshot);
      setSnapshotIdInUrl(id);

      // Copy URL to clipboard (separate try/catch so save success isn't masked)
      try {
        await navigator.clipboard.writeText(window.location.href);
        setShareToast("Link copied!");
      } catch {
        // Clipboard may fail in insecure contexts — still show the URL updated
        setShareToast("Snapshot saved! Copy the URL to share.");
      }
      setTimeout(() => setShareToast(null), 2500);
    } catch (err) {
      console.error("Failed to save snapshot:", err);
      setShareToast("Failed to save snapshot");
      setTimeout(() => setShareToast(null), 2500);
    } finally {
      setIsSavingSnapshot(false);
    }
  }, [isSavingSnapshot, entities, edges, expandedNodes, centerNodeId, pathNodeIds, entityFilter, currentQuery, selectionHistory, selectedEntity]);

  // Restore snapshot from URL on mount
  useEffect(() => {
    const snapshotId = getSnapshotIdFromUrl();
    if (!snapshotId) return;

    loadSnapshot(snapshotId).then((snapshot) => {
      if (!snapshot) return;

      // Apply saved positions as layoutX/layoutY so GraphCanvas renders instantly
      const entitiesWithLayout: Entity[] = snapshot.entities.map((e) => {
        const pos = snapshot.node_positions[e.id];
        return pos ? { ...e, layoutX: pos.x, layoutY: pos.y } : e;
      });

      setCurrentQuery(snapshot.query);
      setEntities(entitiesWithLayout);
      setEdges(snapshot.edges);
      setExpandedNodes(snapshot.expanded_nodes);
      setCenterNodeId(snapshot.center_node_id);
      setPathNodeIds(snapshot.path_node_ids);
      setEntityFilter(snapshot.entity_filter);
      setSelectedEdge(null);

      // Restore exploration path (selection history)
      const restoredHistory = snapshot.selection_history ?? [];
      if (restoredHistory.length > 0) {
        setSelectionHistory(restoredHistory);
      }

      // Restore selected entity — use saved selection, fall back to center node
      const selectedId = snapshot.selected_entity_id;
      const selected = selectedId
        ? entitiesWithLayout.find((e) => e.id === selectedId)
        : entitiesWithLayout.find((e) => e.id === snapshot.center_node_id);
      if (selected) {
        setSelectedEntity(selected);
        // If no history was saved, at least add the selected entity
        if (restoredHistory.length === 0) {
          addToSelectionHistory(selected);
        }
      }

      // Open sidebars so exploration path and overview are visible
      setSidebarOpen(true);
      setRightSidebarCollapsed(false);

      // Cache for reset
      initialGraphStateRef.current = {
        entities: entitiesWithLayout,
        edges: snapshot.edges,
        centerNodeId: snapshot.center_node_id,
      };

      setGraphKey((k) => k + 1);
      setChatExpanded(false);
    }).catch(() => {
      // Silently ignore — user will see empty state
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const graphLoaded = entities.length > 0;

  // Edges that connect any two nodes in the selection history
  const historyNodeIds = new Set(selectionHistory.map((e) => e.id));
  const historyEdgeIds = new Set(
    edges
      .filter((e) => historyNodeIds.has(e.source) && historyNodeIds.has(e.target))
      .map((e) => e.id)
  );

  // Convert selectionHistory (newest-first) → PathNode[] (oldest-first) for Deep Think
  const deepThinkPath = useMemo(() => {
    const ordered = [...selectionHistory].reverse();
    return ordered.map((entity, i) => {
      const next = ordered[i + 1];
      const connEdge = next
        ? edges.find(
            (e) =>
              (e.source === entity.id && e.target === next.id) ||
              (e.target === entity.id && e.source === next.id)
          )
        : undefined;
      return {
        entityId: entity.id,
        entityName: entity.name,
        entityType: entity.type,
        edgePredicate: connEdge?.label ?? connEdge?.predicate,
      };
    });
  }, [selectionHistory, edges]);

  const evidence = selectedEdge?.evidence ?? [];
  const currentSelectionType: "edge" | "node" | null = selectedEdge
    ? "edge"
    : selectedEntity
      ? "node"
      : null;

  const overviewRequest: OverviewStreamRequestPayload | null = useMemo(() => {
    if (!currentSelectionType || !centerNodeId) return null;

    const baseEdges = edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      predicate: edge.predicate,
      label: edge.label,
      score: edge.score,
      provenance: edge.provenance,
      sourceDb: edge.sourceDb,
      evidence: (edge.evidence ?? []).map((ev) => ({
        id: ev.id,
        pmid: ev.pmid,
        title: ev.title,
        year: ev.year,
        snippet: ev.snippet,
        source: ev.source,
        sourceDb: ev.sourceDb,
      })),
      paper_count: edge.paperCount,
      trial_count: edge.trialCount,
      patent_count: edge.patentCount,
      cooccurrence_score: edge.cooccurrenceScore,
    }));

    // Build chronological path: selectionHistory is newest-first, so reverse it.
    // selectionHistory only tracks expanded nodes; append selectedEntity at the tail
    // if it was only single-clicked (not yet in history).
    const path = [...selectionHistory].reverse().map((e) => ({
      id: e.id,
      name: e.name,
      type: e.type as string,
    }));
    const pathTail = path[path.length - 1];
    if (selectedEntity && (!pathTail || pathTail.id !== selectedEntity.id)) {
      path.push({ id: selectedEntity.id, name: selectedEntity.name, type: selectedEntity.type as string });
    }

    return {
      selection_type: currentSelectionType,
      edge_id: currentSelectionType === "edge" ? selectedEdge?.id : undefined,
      node_id: currentSelectionType === "node" ? selectedEntity?.id : undefined,
      center_node_id: centerNodeId,
      entities: entities.map((entity) => ({
        id: entity.id,
        name: entity.name,
        type: entity.type,
      })),
      edges: baseEdges,
      history: overviewHistory.slice(-3).map((h) => ({
        selection_key: h.selectionKey,
        selection_type: h.selectionType,
        summary: h.summary,
      })),
      path,
    };
  }, [
    currentSelectionType,
    centerNodeId,
    edges,
    entities,
    selectedEdge?.id,
    selectedEntity,
    overviewHistory,
    selectionHistory,
  ]);

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
        <a href="/" className="top-nav-logo">BioRender</a>
      </nav>
      <div className="app-layout">
      <div className="blob-bg" aria-hidden="true">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
        <div className="blob blob-4" />
      </div>
      {/* Left Pane - Exploration Path + AI Overview */}
      <aside className={`pane pane-left ${sidebarOpen ? "" : "collapsed"}`}>
        <div className="pane-header">
          <h2 className="path-history-title">Knowledge Exploration Path</h2>
        </div>
        <div className="left-pane-body" ref={leftPaneBodyRef}>
          <div
            className="path-history-list"
            style={{ flex: `0 0 ${graphLoaded ? overviewRatio * 100 : 100}%` }}
          >
            <PathBreadcrumb
              selectionHistory={selectionHistory}
              edges={edges}
              onPrune={handlePruneHistory}
              onClear={() => {
                setSelectionHistory([]);
                setExpansionSnapshots(new Map());
              }}
            />
          </div>
          {graphLoaded && (
            <>
              <div className="pane-resize-handle" onMouseDown={handleDividerMouseDown} />
              <div className="left-pane-overview">
                <AIOverviewCard
                  key={overviewRequest ? `${overviewRequest.selection_type}:${overviewRequest.edge_id ?? overviewRequest.node_id ?? "none"}` : "overview-none"}
                  request={overviewRequest}
                  onComplete={(item) => {
                    setOverviewHistory((prev) => {
                      const deduped = prev.filter(
                        (existing) => existing.selectionKey !== item.selectionKey
                      );
                      return [...deduped, item].slice(-3);
                    });
                  }}
                />
              </div>
            </>
          )}
        </div>
      </aside>

      {/* Centre Pane */}
      <main className="pane pane-centre">
        {/* Floating left-edge tab for left panel toggle */}
        <button
          className={`panel-edge-tab panel-edge-tab-left${sidebarOpen ? " panel-open" : ""}`}
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            {sidebarOpen ? <path d="M15 18l-6-6 6-6" /> : <path d="M9 18l6-6-6-6" />}
          </svg>
        </button>

        {/* Top bar: toolbar + filter */}
        <div className="centre-topbar">
          <Toolbar onFit={handleFit} disabled={!graphLoaded} canReset={graphLoaded && expandedNodes.length > 1} onReset={handleResetExploration} canShare={graphLoaded} onShare={handleSaveSnapshot} isSaving={isSavingSnapshot} />

          {graphLoaded && (
            <EntityFilter entityFilter={entityFilter} onEntityFilterChange={setEntityFilter} />
          )}
        </div>

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

        {/* Share toast */}
        {shareToast && (
          <div className="share-toast">{shareToast}</div>
        )}

        {/* Loading overlay */}
        {isQuerying && (
          <div className="query-loading-overlay">
            <div className="query-loading-spinner" />
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
          historyEdgeIds={historyEdgeIds}
          onNodeSelect={handleNodeSelect}
          onNodeExpand={handleNodeExpand}
          onEdgeSelect={handleEdgeSelect}
          disabledNodeIds={disabledNodeIds}
          fitRequest={fitRequest}
          pathNodeIds={pathNodeIds}
          onPositionsUpdate={handlePositionsUpdate}
        />

        {/* Graph legend (bottom-left) */}
        {graphLoaded && <GraphLegend />}

        {/* Floating right-edge tab for right panel toggle */}
        {(selectedEdge || selectedEntity) && (
          <button
            className={`panel-edge-tab panel-edge-tab-right${!rightSidebarCollapsed ? " panel-open" : ""}`}
            onClick={() => setRightSidebarCollapsed((v) => !v)}
            aria-label={rightSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              {rightSidebarCollapsed ? <path d="M15 18l-6-6 6-6" /> : <path d="M9 18l6-6-6-6" />}
            </svg>
          </button>
        )}

        {/* Chat input */}
        {chatExpanded && (!isQuerying || graphLoaded) && (
          <>
            {graphLoaded && (
              <div
                className="chat-spotlight-backdrop"
                onClick={() => setChatExpanded(false)}
              />
            )}
            <ChatInput
              onSubmit={handleQuery}
              isLoading={isQuerying}
              onCollapse={() => setChatExpanded(false)}
              showCollapse={graphLoaded}
              isLanding={!graphLoaded}
            />
          </>
        )}
        {!chatExpanded && (
          <button
            className="chat-expand-fab"
            onClick={() => setChatExpanded(true)}
            aria-label="Open chat"
            title="Open chat"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        )}
      </main>

      {/* Right Pane */}
      {(selectedEdge || selectedEntity || selectionHistory.length >= 2) && (
        <aside className={`pane pane-right ${rightSidebarCollapsed ? "collapsed" : ""}`}>
          {rightSidebarCollapsed ? (
            <button
              className="right-pane-expand"
              onClick={() => setRightSidebarCollapsed(false)}
              aria-label="Expand sidebar"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
          ) : (
            <div className="right-pane-inner">
              {/* Scrollable middle: entity / edge panels */}
              <div className={`right-pane-middle${activeRightSection === 'deepthink' ? ' section-collapsed' : ''}`}>
                {selectedEdge ? (
                  <EvidencePanel
                    edge={selectedEdge}
                    evidence={evidence}
                    entities={entities}
                    onClose={() => setSelectedEdge(null)}
                  />
                ) : selectedEntity ? (
                  <EntityAdvancedSearchPanel
                    entity={selectedEntity}
                    selectionHistory={selectionHistory}
                    edges={edges}
                  />
                ) : null}
              </div>

              {/* Pinned bottom: Deep Think */}
              {selectionHistory.length >= 1 && (
                <DeepThinkPanel
                  path={deepThinkPath}
                  edges={edges}
                  onOpenChange={(open) => setActiveRightSection(open ? 'deepthink' : 'overview')}
                />
              )}
            </div>
          )}
        </aside>
      )}
      </div>
    </div>
  );
}

export default App;
