import { useRef, useEffect, useCallback } from "react";
import * as THREE from "three";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
} from "d3-force";
import type { SimulationNodeDatum, SimulationLinkDatum } from "d3-force";
import type { Entity, GraphEdge, PathNode } from "../types";
import { ENTITY_COLORS } from "../types";
import "./GraphCanvas.css";

interface Props {
  entities: Entity[];
  edges: GraphEdge[];
  selectedEntityId: string | null;
  selectedEdgeId: string | null;
  expandedNodes: Set<string>;
  path: PathNode[];
  onNodeSelect: (nodeId: string) => void;
  onNodeExpand: (nodeId: string) => void;
  onEdgeSelect: (edgeId: string) => void;
  onAddToPath: (nodeId: string) => void;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  entityType: string;
  color: string;
  size: number;
  mesh?: THREE.Mesh;
  glowMesh?: THREE.Mesh;
  labelSprite?: THREE.Sprite;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string;
  color?: string;
  line?: THREE.Line;
  glowMesh?: THREE.Mesh;
}

const EDGE_COLOR = 0xbdc3c7;
const EDGE_HOVER_WIDTH = 3;
const EDGE_GLOW_WIDTH = 8;
const EDGE_GLOW_OPACITY = 0.25;
const NODE_RADIUS = 14;
const BG_COLOR = 0xf0eee9;

function createNodeGeometry(entityType: string): THREE.BufferGeometry {
  switch (entityType) {
    case "disease": {
      const shape = new THREE.Shape();
      shape.moveTo(0, NODE_RADIUS);
      shape.lineTo(NODE_RADIUS, 0);
      shape.lineTo(0, -NODE_RADIUS);
      shape.lineTo(-NODE_RADIUS, 0);
      shape.closePath();
      return new THREE.ShapeGeometry(shape);
    }
    case "drug": {
      const r = NODE_RADIUS * 0.85;
      const cr = 3;
      const shape = new THREE.Shape();
      shape.moveTo(-r + cr, -r);
      shape.lineTo(r - cr, -r);
      shape.quadraticCurveTo(r, -r, r, -r + cr);
      shape.lineTo(r, r - cr);
      shape.quadraticCurveTo(r, r, r - cr, r);
      shape.lineTo(-r + cr, r);
      shape.quadraticCurveTo(-r, r, -r, r - cr);
      shape.lineTo(-r, -r + cr);
      shape.quadraticCurveTo(-r, -r, -r + cr, -r);
      return new THREE.ShapeGeometry(shape);
    }
    case "pathway": {
      return new THREE.CircleGeometry(NODE_RADIUS, 6);
    }
    case "protein": {
      const shape = new THREE.Shape();
      const r = NODE_RADIUS;
      shape.moveTo(0, r);
      shape.lineTo(r * Math.cos(Math.PI / 6) * -1, -r * Math.sin(Math.PI / 6));
      shape.lineTo(r * Math.cos(Math.PI / 6), -r * Math.sin(Math.PI / 6));
      shape.closePath();
      return new THREE.ShapeGeometry(shape);
    }
    default:
      return new THREE.CircleGeometry(NODE_RADIUS, 32);
  }
}

function createLabelTexture(text: string): THREE.Texture {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const fontSize = 28;
  ctx.font = `500 ${fontSize}px Inter, sans-serif`;
  const metrics = ctx.measureText(text);
  const width = Math.ceil(metrics.width) + 12;
  const height = fontSize + 12;
  canvas.width = width;
  canvas.height = height;
  ctx.font = `500 ${fontSize}px Inter, sans-serif`;
  ctx.fillStyle = "#1A1A1A";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, width / 2, height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  return texture;
}

export default function GraphCanvas({
  entities,
  edges,
  selectedEntityId,
  selectedEdgeId,
  expandedNodes,
  path,
  onNodeSelect,
  onNodeExpand,
  onEdgeSelect,
  onAddToPath,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const hoveredNodeRef = useRef<THREE.Mesh | null>(null);
  const selectedEntityIdRef = useRef<string | null>(selectedEntityId);
  const selectedEdgeIdRef = useRef<string | null>(selectedEdgeId);
  const onNodeSelectRef = useRef(onNodeSelect);
  const onNodeExpandRef = useRef(onNodeExpand);
  const onEdgeSelectRef = useRef(onEdgeSelect);
  const onAddToPathRef = useRef(onAddToPath);
  const pathIds = new Set(path.map((p) => p.entityId));

  selectedEntityIdRef.current = selectedEntityId;
  selectedEdgeIdRef.current = selectedEdgeId;
  onNodeSelectRef.current = onNodeSelect;
  onNodeExpandRef.current = onNodeExpand;
  onEdgeSelectRef.current = onEdgeSelect;
  onAddToPathRef.current = onAddToPath;

  useEffect(() => {
    if (!containerRef.current || entities.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BG_COLOR);

    const camera = new THREE.OrthographicCamera(
      -width / 2, width / 2, height / 2, -height / 2, 0.1, 1000
    );
    camera.position.z = 100;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Build simulation data
    const simNodes: SimNode[] = entities.map((e) => ({
      id: e.id,
      label: e.name,
      entityType: e.type,
      color: e.color ?? ENTITY_COLORS[e.type],
      size: e.size ?? 1,
    }));

    const nodeMap = new Map<string, SimNode>();
    simNodes.forEach((n) => nodeMap.set(n.id, n));

    const simLinks: SimLink[] = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        color: e.color,
      }));

    // Create edge lines first (render behind nodes)
    const edgeMeshes: SimLink[] = [];
    simLinks.forEach((link) => {
      const material = new THREE.LineBasicMaterial({
        color: EDGE_COLOR,
        linewidth: 1,
        transparent: true,
        opacity: 0.6,
      });
      const geometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0, 0, 0),
      ]);
      const line = new THREE.Line(geometry, material);
      line.userData = { edgeId: link.id };
      scene.add(line);
      link.line = line;

      // Glow mesh for edge hover/selection
      const glowColor = link.color ? new THREE.Color(link.color) : new THREE.Color(0x7FB3E0);
      const glowGeo = new THREE.PlaneGeometry(1, 1);
      const glowMat = new THREE.MeshBasicMaterial({
        color: glowColor,
        transparent: true,
        opacity: EDGE_GLOW_OPACITY,
        depthWrite: false,
      });
      const glowMesh = new THREE.Mesh(glowGeo, glowMat);
      glowMesh.position.z = 0.1;
      glowMesh.visible = false;
      scene.add(glowMesh);
      link.glowMesh = glowMesh;

      edgeMeshes.push(link);
    });

    // Create node meshes + labels
    simNodes.forEach((node) => {
      const geometry = createNodeGeometry(node.entityType);
      const material = new THREE.MeshBasicMaterial({
        color: new THREE.Color(node.color),
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData = { nodeId: node.id, nodeSize: node.size };
      mesh.position.z = 1;
      scene.add(mesh);
      node.mesh = mesh;

      const r = NODE_RADIUS * node.size;
      mesh.scale.set(node.size, node.size, 1);

      // Glow (for selected + hover) - radius in local space so it scales with mesh
      const glowGeo = new THREE.CircleGeometry(NODE_RADIUS * 2, 32);
      const glowMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(node.color),
        transparent: true,
        opacity: 0.5,
      });
      const glow = new THREE.Mesh(glowGeo, glowMat);
      glow.position.z = 0.5;
      mesh.add(glow);
      node.glowMesh = glow;
      glow.visible = node.id === selectedEntityIdRef.current;

      // Expanded indicator
      if (expandedNodes.has(node.id)) {
        const dotGeo = new THREE.CircleGeometry(3, 16);
        const dotMat = new THREE.MeshBasicMaterial({
          color: new THREE.Color(node.color),
        });
        const dot = new THREE.Mesh(dotGeo, dotMat);
        dot.position.set(r + 4, r + 4, 2);
        mesh.add(dot);
      }

      // Path highlight
      if (pathIds.has(node.id)) {
        const ringGeo = new THREE.RingGeometry(r + 1, r + 4, 32);
        const ringMat = new THREE.MeshBasicMaterial({ color: 0xf39c12 });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.z = 0.5;
        mesh.add(ring);
      }

      // Label
      const texture = createLabelTexture(node.label);
      const spriteMat = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
      });
      const sprite = new THREE.Sprite(spriteMat);
      const aspect = texture.image.width / texture.image.height;
      sprite.scale.set(aspect * 16, 16, 1);
      sprite.position.set(0, -(r + 14), 2);
      scene.add(sprite);
      node.labelSprite = sprite;
    });

    // Force simulation
    const simulation = forceSimulation(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(120)
      )
      .force("charge", forceManyBody().strength(-400))
      .force("center", forceCenter(0, 0))
      .force("collide", forceCollide((d) => NODE_RADIUS * (d.size ?? 1) * 2.5))
      .alphaDecay(0.02);

    simulation.on("tick", () => {
      simNodes.forEach((node) => {
        const r = NODE_RADIUS * node.size;
        if (node.mesh && node.x !== undefined && node.y !== undefined) {
          node.mesh.position.x = node.x;
          node.mesh.position.y = node.y;
        }
        if (node.labelSprite && node.x !== undefined && node.y !== undefined) {
          node.labelSprite.position.x = node.x;
          node.labelSprite.position.y = node.y - (r + 14);
        }
      });

      simLinks.forEach((link) => {
        const s = link.source as SimNode;
        const t = link.target as SimNode;
        if (link.line && s.x !== undefined && s.y !== undefined && t.x !== undefined && t.y !== undefined) {
          const positions = link.line.geometry.attributes.position as THREE.BufferAttribute;
          positions.setXY(0, s.x, s.y);
          positions.setXY(1, t.x, t.y);
          positions.needsUpdate = true;

          const isSelected = link.id === selectedEdgeIdRef.current;
          const mat = link.line.material as THREE.LineBasicMaterial;
          mat.color.setHex(isSelected ? 0x4A90D9 : EDGE_COLOR);
          mat.opacity = isSelected ? 1 : 0.6;

          if (link.glowMesh) {
            const dx = t.x - s.x;
            const dy = t.y - s.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            link.glowMesh.position.set((s.x + t.x) / 2, (s.y + t.y) / 2, 0.1);
            link.glowMesh.rotation.z = Math.atan2(dy, dx);
            link.glowMesh.scale.set(dist, EDGE_GLOW_WIDTH, 1);
          }
        }
      });
    });

    // Helper: check if a node is an endpoint of the given edge
    function isConnectedToEdge(nodeId: string, edgeId: string): boolean {
      const link = simLinks.find((l) => l.id === edgeId);
      if (!link) return false;
      const s = (link.source as SimNode).id ?? link.source;
      const t = (link.target as SimNode).id ?? link.target;
      return s === nodeId || t === nodeId;
    }

    // Interaction state
    const raycaster = new THREE.Raycaster();
    raycaster.params.Line = { threshold: 5 };
    const mouse = new THREE.Vector2();
    let hoveredNode: THREE.Mesh | null = null;
    let hoveredEdgeLine: THREE.Line | null = null;
    let clickTimer: ReturnType<typeof setTimeout> | null = null;
    let isDragging = false;
    let dragStart = { x: 0, y: 0 };
    let panStart = { x: 0, y: 0 };
    let isPanning = false;

    function screenToWorld(clientX: number, clientY: number) {
      const rect = container.getBoundingClientRect();
      mouse.x = ((clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    }

    function getIntersectedNode(event: MouseEvent): THREE.Mesh | null {
      screenToWorld(event.clientX, event.clientY);
      raycaster.setFromCamera(mouse, camera);
      const nodeMeshes = simNodes
        .map((n) => n.mesh)
        .filter(Boolean) as THREE.Mesh[];
      const intersects = raycaster.intersectObjects(nodeMeshes, false);
      return intersects.length > 0 ? (intersects[0].object as THREE.Mesh) : null;
    }

    function getIntersectedEdge(event: MouseEvent): THREE.Line | null {
      screenToWorld(event.clientX, event.clientY);
      raycaster.setFromCamera(mouse, camera);
      const lines = simLinks
        .map((l) => l.line)
        .filter(Boolean) as THREE.Line[];
      const intersects = raycaster.intersectObjects(lines);
      return intersects.length > 0 ? (intersects[0].object as THREE.Line) : null;
    }

    // Mouse move (hover)
    const handleMouseMove = (e: MouseEvent) => {
      if (isPanning) {
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        camera.position.x = panStart.x - dx;
        camera.position.y = panStart.y + dy;
        camera.updateProjectionMatrix();
        return;
      }

      const node = getIntersectedNode(e);
      if (node && node !== hoveredNode) {
        if (hoveredNode) {
          const s = (hoveredNode.userData.nodeSize as number) ?? 1;
          hoveredNode.scale.set(s, s, 1);
        }
        const s = (node.userData.nodeSize as number) ?? 1;
        node.scale.set(s * 1.15, s * 1.15, 1);
        hoveredNode = node;
        hoveredNodeRef.current = node;
        container.style.cursor = "pointer";
      } else if (!node && hoveredNode) {
        const s = (hoveredNode.userData.nodeSize as number) ?? 1;
        hoveredNode.scale.set(s, s, 1);
        hoveredNode = null;
        hoveredNodeRef.current = null;
        container.style.cursor = "default";
      }

      if (!node) {
        const edge = getIntersectedEdge(e);
        if (edge && edge !== hoveredEdgeLine) {
          // Reset previous hovered edge (only if it's not the selected edge)
          if (hoveredEdgeLine) {
            const isSelected = hoveredEdgeLine.userData.edgeId === selectedEdgeIdRef.current;
            if (!isSelected) {
              const mat = hoveredEdgeLine.material as THREE.LineBasicMaterial;
              mat.color.setHex(EDGE_COLOR);
              mat.opacity = 0.6;
            }
          }
          // Highlight new hovered edge (only if it's not already selected)
          const isSelected = edge.userData.edgeId === selectedEdgeIdRef.current;
          if (!isSelected) {
            const mat = edge.material as THREE.LineBasicMaterial;
            mat.color.setHex(0x7FB3E0);
            mat.opacity = 0.8;
          }
          hoveredEdgeLine = edge;
        } else if (!edge && hoveredEdgeLine) {
          const isSelected = hoveredEdgeLine.userData.edgeId === selectedEdgeIdRef.current;
          if (!isSelected) {
            const mat = hoveredEdgeLine.material as THREE.LineBasicMaterial;
            mat.color.setHex(EDGE_COLOR);
            mat.opacity = 0.6;
          }
          hoveredEdgeLine = null;
        }
        container.style.cursor = edge ? "pointer" : "default";
      }
    };

    const handleMouseLeave = () => {
      if (hoveredNode) {
        const s = (hoveredNode.userData.nodeSize as number) ?? 1;
        hoveredNode.scale.set(s, s, 1);
        hoveredNode = null;
        hoveredNodeRef.current = null;
        container.style.cursor = "default";
      }
      if (hoveredEdgeLine) {
        const isSelected = hoveredEdgeLine.userData.edgeId === selectedEdgeIdRef.current;
        if (!isSelected) {
          const mat = hoveredEdgeLine.material as THREE.LineBasicMaterial;
          mat.color.setHex(EDGE_COLOR);
          mat.opacity = 0.6;
        }
        hoveredEdgeLine = null;
      }
    };

    // Mouse down
    const handleMouseDown = (e: MouseEvent) => {
      if (e.button === 0) {
        const node = getIntersectedNode(e);
        if (!node) {
          isPanning = true;
          dragStart = { x: e.clientX, y: e.clientY };
          panStart = { x: camera.position.x, y: camera.position.y };
        }
      }
    };

    // Mouse up / click
    const handleMouseUp = (e: MouseEvent) => {
      if (isPanning) {
        const dx = Math.abs(e.clientX - dragStart.x);
        const dy = Math.abs(e.clientY - dragStart.y);
        isPanning = false;
        if (dx > 5 || dy > 5) return;
      }

      if (e.button === 0) {
        const node = getIntersectedNode(e);
        if (node) {
          const nodeId = node.userData.nodeId as string;
          if (clickTimer) {
            clearTimeout(clickTimer);
            clickTimer = null;
            onNodeExpandRef.current(nodeId);
          } else {
            clickTimer = setTimeout(() => {
              clickTimer = null;
              onNodeSelectRef.current(nodeId);
            }, 150);
          }
          return;
        }

        const edge = getIntersectedEdge(e);
        if (edge) {
          onEdgeSelectRef.current(edge.userData.edgeId as string);
        }
      }
    };

    // Right-click → add to path
    const handleContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      const node = getIntersectedNode(e);
      if (node) {
        onAddToPathRef.current(node.userData.nodeId as string);
      }
    };

    // Scroll → zoom
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
      camera.zoom = Math.max(0.2, Math.min(5, camera.zoom / zoomFactor));
      camera.updateProjectionMatrix();
    };

    container.addEventListener("mousemove", handleMouseMove);
    container.addEventListener("mouseleave", handleMouseLeave);
    container.addEventListener("mousedown", handleMouseDown);
    container.addEventListener("mouseup", handleMouseUp);
    container.addEventListener("contextmenu", handleContextMenu);
    container.addEventListener("wheel", handleWheel, { passive: false });

    // Resize
    const handleResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.left = -w / 2;
      camera.right = w / 2;
      camera.top = h / 2;
      camera.bottom = -h / 2;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    const resizeObs = new ResizeObserver(handleResize);
    resizeObs.observe(container);

    // Render loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      simNodes.forEach((node) => {
        if (node.glowMesh) {
          const isHovered = hoveredNodeRef.current === node.mesh;
          const isEdgeEndpoint = selectedEdgeIdRef.current !== null &&
            isConnectedToEdge(node.id, selectedEdgeIdRef.current);
          node.glowMesh.visible = isHovered || isEdgeEndpoint;
        }
      });
      simLinks.forEach((link) => {
        if (link.glowMesh) {
          const isHovered = hoveredEdgeLine !== null &&
            hoveredEdgeLine.userData.edgeId === link.id;
          const isSelected = link.id === selectedEdgeIdRef.current;
          link.glowMesh.visible = isHovered || isSelected;
        }
      });
      renderer.render(scene, camera);
    };
    animate();

    cleanupRef.current = () => {
      cancelAnimationFrame(animId);
      simulation.stop();
      container.removeEventListener("mousemove", handleMouseMove);
      container.removeEventListener("mouseleave", handleMouseLeave);
      container.removeEventListener("mousedown", handleMouseDown);
      container.removeEventListener("mouseup", handleMouseUp);
      container.removeEventListener("contextmenu", handleContextMenu);
      container.removeEventListener("wheel", handleWheel);
      resizeObs.disconnect();
      simLinks.forEach((link) => {
        if (link.glowMesh) {
          link.glowMesh.geometry.dispose();
          (link.glowMesh.material as THREE.MeshBasicMaterial).dispose();
        }
      });
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };

    return () => {
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entities, edges]);

  if (entities.length === 0) {
    return <div className="graph-empty" />;
  }

  return <div ref={containerRef} className="graph-container" />;
}
