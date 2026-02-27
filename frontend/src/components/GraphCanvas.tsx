import { useRef, useEffect } from "react";
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
  expandedNodes: string[];
  path: PathNode[];
  historyEdgeIds: Set<string>;
  onNodeSelect: (nodeId: string) => void;
  onNodeExpand: (nodeId: string) => void;
  onEdgeSelect: (edgeId: string) => void;
  onAddToPath: (nodeId: string) => void;
  disabledNodeIds: Set<string>;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  entityType: string;
  color: string;
  size: number;
  mesh?: THREE.Mesh;
  nodeSprite?: THREE.Sprite;
  labelSprite?: THREE.Sprite;
  animProgress: number; // 0 = just spawned, 1 = fully visible
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string;
  label?: string;
  color?: string;
  line?: THREE.Line;
  glowMesh?: THREE.Mesh;
}

const EDGE_COLOR = 0xbdc3c7;
const EDGE_GLOW_WIDTH = 4;
const EDGE_GLOW_OPACITY = 0.25;
const NODE_RADIUS = 14;
const BG_COLOR = 0xf0eee9;
const BORDER_INNER_OFFSET = 1;
const BORDER_OUTER_OFFSET = 2.5;

// Canvas-rendered node texture constants
const NODE_TEXTURE_SIZE = 256;
const NODE_CIRCLE_RADIUS = 80;
const NODE_GLOW_RADIUS = 120;
const NODE_ICON_RADIUS = 32;
// 45 * (80/256) ≈ 14 = NODE_RADIUS — keeps border rings aligned with visible circle
const NODE_SPRITE_WORLD_SIZE = 45;
const LABEL_PILL_PADDING_X = 10;
const LABEL_PILL_PADDING_Y = 6;

// --- Color utilities ---

function colorWithAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function lightenColor(hex: string, amount: number): string {
  const r = Math.min(255, parseInt(hex.slice(1, 3), 16) + Math.round(255 * amount));
  const g = Math.min(255, parseInt(hex.slice(3, 5), 16) + Math.round(255 * amount));
  const b = Math.min(255, parseInt(hex.slice(5, 7), 16) + Math.round(255 * amount));
  return `rgb(${r},${g},${b})`;
}

function darkenColor(hex: string, amount: number): string {
  const r = Math.max(0, parseInt(hex.slice(1, 3), 16) - Math.round(255 * amount));
  const g = Math.max(0, parseInt(hex.slice(3, 5), 16) - Math.round(255 * amount));
  const b = Math.max(0, parseInt(hex.slice(5, 7), 16) - Math.round(255 * amount));
  return `rgb(${r},${g},${b})`;
}

// --- Icon drawing functions ---

function drawGeneIcon(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  // Double helix: two sine-wave strands + horizontal rungs
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  const steps = 20;
  const amplitude = r * 0.35;
  const height = r * 1.6;
  // First strand
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const y = cy - height / 2 + t * height;
    const x = cx + Math.sin(t * Math.PI * 2) * amplitude;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
  // Second strand
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const y = cy - height / 2 + t * height;
    const x = cx - Math.sin(t * Math.PI * 2) * amplitude;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
  // Rungs
  ctx.lineWidth = 1.5;
  for (let i = 0; i <= 4; i++) {
    const t = (i + 0.5) / 5;
    const y = cy - height / 2 + t * height;
    const x1 = cx + Math.sin(t * Math.PI * 2) * amplitude;
    const x2 = cx - Math.sin(t * Math.PI * 2) * amplitude;
    ctx.beginPath();
    ctx.moveTo(x1, y);
    ctx.lineTo(x2, y);
    ctx.stroke();
  }
}

function drawDiseaseIcon(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  // Warning triangle with exclamation mark
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 2.5;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  const triR = r * 1.1;
  ctx.beginPath();
  ctx.moveTo(cx, cy - triR);
  ctx.lineTo(cx - triR * Math.cos(Math.PI / 6), cy + triR * Math.sin(Math.PI / 6));
  ctx.lineTo(cx + triR * Math.cos(Math.PI / 6), cy + triR * Math.sin(Math.PI / 6));
  ctx.closePath();
  ctx.stroke();
  // Exclamation mark
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, cy - triR * 0.4);
  ctx.lineTo(cx, cy + triR * 0.1);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cy + triR * 0.3, 2, 0, Math.PI * 2);
  ctx.fill();
}

function drawDrugIcon(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  // Pill capsule (tilted, two-tone halves)
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-Math.PI / 6);
  const w = r * 1.4;
  const h = r * 0.65;
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 2.5;
  // Left half (outline only)
  ctx.beginPath();
  ctx.moveTo(0, -h);
  ctx.lineTo(-w + h, -h);
  ctx.arc(-w + h, 0, h, -Math.PI / 2, Math.PI / 2, true);
  ctx.lineTo(0, h);
  ctx.stroke();
  // Right half (filled semi-transparent)
  ctx.fillStyle = "rgba(255,255,255,0.3)";
  ctx.beginPath();
  ctx.moveTo(0, -h);
  ctx.lineTo(w - h, -h);
  ctx.arc(w - h, 0, h, -Math.PI / 2, Math.PI / 2, false);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  // Center divider
  ctx.beginPath();
  ctx.moveTo(0, -h);
  ctx.lineTo(0, h);
  ctx.stroke();
  ctx.restore();
}

function drawPathwayIcon(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  // Mini graph: three connected dots in triangle arrangement
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  const dr = r * 0.7;
  const dotR = r * 0.15;
  const points = [
    { x: cx, y: cy - dr },
    { x: cx - dr * 0.87, y: cy + dr * 0.5 },
    { x: cx + dr * 0.87, y: cy + dr * 0.5 },
  ];
  // Edges
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      ctx.beginPath();
      ctx.moveTo(points[i].x, points[i].y);
      ctx.lineTo(points[j].x, points[j].y);
      ctx.stroke();
    }
  }
  // Dots
  for (const p of points) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, dotR, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawProteinIcon(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  // Hexagonal benzene ring with vertex dots + inner circle
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  const hexR = r * 0.8;
  const dotR = r * 0.1;
  // Hexagon
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    const x = cx + hexR * Math.cos(angle);
    const y = cy + hexR * Math.sin(angle);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.stroke();
  // Inner circle (benzene)
  ctx.beginPath();
  ctx.arc(cx, cy, hexR * 0.5, 0, Math.PI * 2);
  ctx.stroke();
  // Vertex dots
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    const x = cx + hexR * Math.cos(angle);
    const y = cy + hexR * Math.sin(angle);
    ctx.beginPath();
    ctx.arc(x, y, dotR, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawEntityIcon(ctx: CanvasRenderingContext2D, entityType: string, cx: number, cy: number, r: number) {
  switch (entityType) {
    case "gene": drawGeneIcon(ctx, cx, cy, r); break;
    case "disease": drawDiseaseIcon(ctx, cx, cy, r); break;
    case "drug": drawDrugIcon(ctx, cx, cy, r); break;
    case "pathway": drawPathwayIcon(ctx, cx, cy, r); break;
    case "protein": drawProteinIcon(ctx, cx, cy, r); break;
  }
}

/** Renders glow + gradient circle + icon + border onto a 256x256 canvas texture */
function createNodeTexture(entityType: string, color: string): THREE.CanvasTexture {
  const size = NODE_TEXTURE_SIZE;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const cx = size / 2;
  const cy = size / 2;

  // 1. Outer glow aura (entity color → transparent)
  const glowGrad = ctx.createRadialGradient(cx, cy, NODE_CIRCLE_RADIUS * 0.8, cx, cy, NODE_GLOW_RADIUS);
  glowGrad.addColorStop(0, colorWithAlpha(color, 0.18));
  glowGrad.addColorStop(1, colorWithAlpha(color, 0));
  ctx.fillStyle = glowGrad;
  ctx.fillRect(0, 0, size, size);

  // 2. Main circle with depth gradient (light center → full color → darkened rim)
  const circleGrad = ctx.createRadialGradient(
    cx - NODE_CIRCLE_RADIUS * 0.2, cy - NODE_CIRCLE_RADIUS * 0.2, 0,
    cx, cy, NODE_CIRCLE_RADIUS
  );
  circleGrad.addColorStop(0, lightenColor(color, 0.35));
  circleGrad.addColorStop(0.6, color);
  circleGrad.addColorStop(1, darkenColor(color, 0.15));
  ctx.beginPath();
  ctx.arc(cx, cy, NODE_CIRCLE_RADIUS, 0, Math.PI * 2);
  ctx.fillStyle = circleGrad;
  ctx.fill();

  // 3. Entity icon overlay
  drawEntityIcon(ctx, entityType, cx, cy, NODE_ICON_RADIUS);

  // 3. Thin white border stroke
  ctx.strokeStyle = "rgba(255,255,255,0.6)";
  ctx.lineWidth = 2;
  ctx.stroke();


  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  return texture;
}

// Cache by "entityType:color" — only ~5 unique textures ever needed
const nodeTextureCache = new Map<string, THREE.CanvasTexture>();

function getNodeTexture(entityType: string, color: string): THREE.CanvasTexture {
  const key = `${entityType}:${color}`;
  let tex = nodeTextureCache.get(key);
  if (!tex) {
    tex = createNodeTexture(entityType, color);
    nodeTextureCache.set(key, tex);
  }
  return tex;
}

/** Circular border ring — replaces per-shape createBorderGeometry */
function createBorderRing(innerR: number, outerR: number): THREE.RingGeometry {
  return new THREE.RingGeometry(innerR, outerR, 48);
}

function createLabelTexture(text: string): THREE.Texture {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const fontSize = 28;
  ctx.font = `500 ${fontSize}px Inter, sans-serif`;
  const metrics = ctx.measureText(text);
  const textWidth = Math.ceil(metrics.width);
  const width = textWidth + LABEL_PILL_PADDING_X * 2 + 12;
  const height = fontSize + LABEL_PILL_PADDING_Y * 2 + 12;
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

function createNumberBadgeTexture(n: number): THREE.Texture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.font = "bold 38px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#1A1A1A";
  ctx.fillText(String(n), size / 2, size / 2);
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
  historyEdgeIds,
  onNodeSelect,
  onNodeExpand,
  onEdgeSelect,
  onAddToPath,
  disabledNodeIds,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const hoveredNodeRef = useRef<THREE.Mesh | null>(null);
  const selectedEntityIdRef = useRef<string | null>(selectedEntityId);
  const selectedEdgeIdRef = useRef<string | null>(selectedEdgeId);
  const historyEdgeIdsRef = useRef<Set<string>>(historyEdgeIds);
  const onNodeSelectRef = useRef(onNodeSelect);
  const onNodeExpandRef = useRef(onNodeExpand);
  const onEdgeSelectRef = useRef(onEdgeSelect);
  const onAddToPathRef = useRef(onAddToPath);
  const disabledNodeIdsRef = useRef(disabledNodeIds);
  const pathIds = new Set(path.map((p) => p.entityId));

  // Position persistence for smooth incremental updates (expand)
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(
    new Map()
  );
  const isInitialRenderRef = useRef(true);

  selectedEntityIdRef.current = selectedEntityId;
  selectedEdgeIdRef.current = selectedEdgeId;
  historyEdgeIdsRef.current = historyEdgeIds;
  onNodeSelectRef.current = onNodeSelect;
  onNodeExpandRef.current = onNodeExpand;
  onEdgeSelectRef.current = onEdgeSelect;
  onAddToPathRef.current = onAddToPath;
  disabledNodeIdsRef.current = disabledNodeIds;

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

    // Build simulation data — restore saved positions for existing nodes
    const simNodes: SimNode[] = entities.map((e) => {
      const savedPos = nodePositionsRef.current.get(e.id);
      return {
        id: e.id,
        label: e.name,
        entityType: e.type,
        color: e.color ?? ENTITY_COLORS[e.type],
        size: e.size ?? 1,
        // New nodes (no saved position) start invisible during expansions
        animProgress: (isInitialRenderRef.current || savedPos) ? 1 : 0,
        ...(savedPos ? { x: savedPos.x, y: savedPos.y } : {}),
      };
    });

    const nodeMap = new Map<string, SimNode>();
    simNodes.forEach((n) => nodeMap.set(n.id, n));

    const simLinks: SimLink[] = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        id: e.id,
        label: e.label,
        source: e.source,
        target: e.target,
        color: e.color,
      }));

    // Position new nodes (no saved position) near connected existing nodes
    simNodes.forEach((node) => {
      if (node.x !== undefined && node.y !== undefined) return; // already positioned
      const neighbors = simLinks
        .filter((l) => {
          const sId = typeof l.source === "string" ? l.source : (l.source as SimNode).id;
          const tId = typeof l.target === "string" ? l.target : (l.target as SimNode).id;
          return sId === node.id || tId === node.id;
        })
        .map((l) => {
          const sId = typeof l.source === "string" ? l.source : (l.source as SimNode).id;
          const tId = typeof l.target === "string" ? l.target : (l.target as SimNode).id;
          const otherId = sId === node.id ? tId : sId;
          return nodeMap.get(otherId);
        })
        .filter((n): n is SimNode => !!n && n.x !== undefined && n.y !== undefined);

      if (neighbors.length > 0) {
        const avgX = neighbors.reduce((s, n) => s + n.x!, 0) / neighbors.length;
        const avgY = neighbors.reduce((s, n) => s + n.y!, 0) / neighbors.length;
        const jitter = () => (Math.random() - 0.5) * 60;
        node.x = avgX + jitter();
        node.y = avgY + jitter();
      }
    });

    // Build adjacency list for BFS path-finding along expansion trail
    const adj = new Map<string, { neighbor: string; edgeId: string }[]>();
    simLinks.forEach((l) => {
      const sId = typeof l.source === "string" ? l.source : (l.source as SimNode).id;
      const tId = typeof l.target === "string" ? l.target : (l.target as SimNode).id;
      if (!adj.has(sId)) adj.set(sId, []);
      if (!adj.has(tId)) adj.set(tId, []);
      adj.get(sId)!.push({ neighbor: tId, edgeId: l.id });
      adj.get(tId)!.push({ neighbor: sId, edgeId: l.id });
    });

    function bfsPathEdges(startId: string, endId: string): string[] {
      if (startId === endId) return [];
      const visited = new Set<string>([startId]);
      const queue: { nodeId: string; edgeTrail: string[] }[] = [
        { nodeId: startId, edgeTrail: [] },
      ];
      while (queue.length > 0) {
        const { nodeId, edgeTrail } = queue.shift()!;
        for (const { neighbor, edgeId } of adj.get(nodeId) ?? []) {
          if (visited.has(neighbor)) continue;
          const newTrail = [...edgeTrail, edgeId];
          if (neighbor === endId) return newTrail;
          visited.add(neighbor);
          queue.push({ nodeId: neighbor, edgeTrail: newTrail });
        }
      }
      return [];
    }

    // Collect all edges on the expansion trail
    const expansionEdgeIds = new Set<string>();
    for (let i = 1; i < expandedNodes.length; i++) {
      for (const edgeId of bfsPathEdges(expandedNodes[i - 1], expandedNodes[i])) {
        expansionEdgeIds.add(edgeId);
      }
    }
    const expandedNodeSet = new Set(expandedNodes);

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
    const meshToSimNode = new Map<THREE.Mesh, SimNode>();

    simNodes.forEach((node) => {
      // Invisible hit mesh for raycasting (opacity:0, not visible:false — raycaster skips visible:false)
      const hitGeo = new THREE.CircleGeometry(NODE_RADIUS, 32);
      const hitMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0,
        depthWrite: false,
      });
      const hitMesh = new THREE.Mesh(hitGeo, hitMat);
      hitMesh.userData = { nodeId: node.id, nodeSize: node.size };
      hitMesh.position.z = 1;
      const initScale = node.animProgress < 1 ? 0.001 : node.size;
      hitMesh.scale.set(initScale, initScale, 1);
      scene.add(hitMesh);
      node.mesh = hitMesh;
      meshToSimNode.set(hitMesh, node);

      // Visual sprite with cached canvas texture
      const tex = getNodeTexture(node.entityType, node.color);
      const spriteMat = new THREE.SpriteMaterial({ map: tex, transparent: true });
      const nodeSprite = new THREE.Sprite(spriteMat);
      const spriteScale = NODE_SPRITE_WORLD_SIZE * node.size;
      const initSpriteScale = node.animProgress < 1 ? 0.001 : spriteScale;
      nodeSprite.scale.set(initSpriteScale, initSpriteScale, 1);
      if (node.animProgress < 1) spriteMat.opacity = 0;
      nodeSprite.position.z = 1;
      scene.add(nodeSprite);
      node.nodeSprite = nodeSprite;

      const r = NODE_RADIUS * node.size;

      // Expansion border ring + number badge
      if (expandedNodeSet.has(node.id)) {
        const ringGeo = createBorderRing(
          NODE_RADIUS + BORDER_INNER_OFFSET,
          NODE_RADIUS + BORDER_OUTER_OFFSET
        );
        const ringMat = new THREE.MeshBasicMaterial({ color: 0x000000 });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.z = 0.5;
        hitMesh.add(ring);

        const order = expandedNodes.indexOf(node.id) + 1;
        const badgeTexture = createNumberBadgeTexture(order);
        const badgeMat = new THREE.SpriteMaterial({ map: badgeTexture, transparent: true });
        const badge = new THREE.Sprite(badgeMat);
        // Counter-scale so badge size stays constant regardless of node.size
        const inv = 1 / node.size;
        badge.scale.set(18 * inv, 18 * inv, 1);
        badge.position.set(0, 0, 2);
        hitMesh.add(badge);
      }

      // Path highlight
      if (pathIds.has(node.id)) {
        const ringGeo = createBorderRing(
          NODE_RADIUS + BORDER_INNER_OFFSET,
          NODE_RADIUS + BORDER_OUTER_OFFSET
        );
        const ringMat = new THREE.MeshBasicMaterial({ color: 0xf39c12 });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.z = 0.5;
        hitMesh.add(ring);
      }

      // Label
      const texture = createLabelTexture(node.label);
      const labelMat = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
      });
      if (node.animProgress < 1) labelMat.opacity = 0;
      const labelSprite = new THREE.Sprite(labelMat);
      const textureImage = texture.source.data as { width: number; height: number };
      const aspect = textureImage.width / textureImage.height;
      labelSprite.scale.set(aspect * 16, 16, 1);
      labelSprite.position.set(0, -(r + 14), 2);
      scene.add(labelSprite);
      node.labelSprite = labelSprite;
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

    // Lower alpha for incremental updates so existing nodes barely move
    const isIncremental = !isInitialRenderRef.current;
    if (isIncremental) {
      simulation.alpha(0.3);
    }
    isInitialRenderRef.current = false;

    simulation.on("tick", () => {
      simNodes.forEach((node) => {
        const r = NODE_RADIUS * node.size;
        if (node.x !== undefined && node.y !== undefined) {
          nodePositionsRef.current.set(node.id, { x: node.x, y: node.y });
        }
        if (node.mesh && node.x !== undefined && node.y !== undefined) {
          node.mesh.position.x = node.x;
          node.mesh.position.y = node.y;
        }
        if (node.nodeSprite && node.x !== undefined && node.y !== undefined) {
          node.nodeSprite.position.x = node.x;
          node.nodeSprite.position.y = node.y;
        }
        if (node.labelSprite && node.x !== undefined && node.y !== undefined) {
          node.labelSprite.position.x = node.x;
          node.labelSprite.position.y = node.y - (r + 14);
        }

        // Dim disabled (non-frontier) nodes, respecting fade-in animation
        const isDisabled = disabledNodeIdsRef.current.has(node.id);
        const baseOpacity = isDisabled ? 0.55 : 1.0;
        const eased = node.animProgress >= 1 ? 1 : node.animProgress * (2 - node.animProgress);
        if (node.nodeSprite) {
          (node.nodeSprite.material as THREE.SpriteMaterial).opacity = baseOpacity * eased;
        }
        if (node.labelSprite) {
          (node.labelSprite.material as THREE.SpriteMaterial).opacity = baseOpacity * eased;
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
          const isExpansionPath = expansionEdgeIds.has(link.id);
          const eitherDisabled = disabledNodeIdsRef.current.has(s.id) || disabledNodeIdsRef.current.has(t.id);
          const mat = link.line.material as THREE.LineBasicMaterial;
          // Fade-in edges connected to new nodes
          const edgeAnimProgress = Math.min(s.animProgress ?? 1, t.animProgress ?? 1);
          const edgeEased = edgeAnimProgress >= 1 ? 1 : edgeAnimProgress * (2 - edgeAnimProgress);
          if (isSelected) {
            mat.color.setHex(0x4A90D9);
            mat.opacity = 1 * edgeEased;
          } else if (isExpansionPath) {
            mat.color.setHex(0x000000);
            mat.opacity = 1.0 * edgeEased;
          } else if (eitherDisabled) {
            mat.color.setHex(EDGE_COLOR);
            mat.opacity = 0.3 * edgeEased;
          } else {
            mat.color.setHex(EDGE_COLOR);
            mat.opacity = 0.6 * edgeEased;
          }

          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (link.glowMesh) {
            link.glowMesh.position.set((s.x + t.x) / 2, (s.y + t.y) / 2, 0.1);
            link.glowMesh.rotation.z = Math.atan2(dy, dx);
            link.glowMesh.scale.set(dist, EDGE_GLOW_WIDTH, 1);
          }
        }
      });
    });

    // Interaction state
    const raycaster = new THREE.Raycaster();
    raycaster.params.Line = { threshold: 5 };
    const mouse = new THREE.Vector2();
    let hoveredNode: THREE.Mesh | null = null;
    let hoveredEdgeLine: THREE.Line | null = null;
    let clickTimer: ReturnType<typeof setTimeout> | null = null;
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
        .filter((n) => !disabledNodeIdsRef.current.has(n.id))
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
        // Reset previous hovered node
        if (hoveredNode) {
          const s = (hoveredNode.userData.nodeSize as number) ?? 1;
          hoveredNode.scale.set(s, s, 1);
          const prevSimN = meshToSimNode.get(hoveredNode);
          if (prevSimN?.nodeSprite) {
            const ss = NODE_SPRITE_WORLD_SIZE * s;
            prevSimN.nodeSprite.scale.set(ss, ss, 1);
          }
        }
        // Scale up new hovered node
        const s = (node.userData.nodeSize as number) ?? 1;
        node.scale.set(s * 1.15, s * 1.15, 1);
        const simN = meshToSimNode.get(node);
        if (simN?.nodeSprite) {
          const ss = NODE_SPRITE_WORLD_SIZE * s * 1.15;
          simN.nodeSprite.scale.set(ss, ss, 1);
        }
        hoveredNode = node;
        hoveredNodeRef.current = node;
        container.style.cursor = "pointer";
      } else if (!node && hoveredNode) {
        const s = (hoveredNode.userData.nodeSize as number) ?? 1;
        hoveredNode.scale.set(s, s, 1);
        const simN = meshToSimNode.get(hoveredNode);
        if (simN?.nodeSprite) {
          const ss = NODE_SPRITE_WORLD_SIZE * s;
          simN.nodeSprite.scale.set(ss, ss, 1);
        }
        hoveredNode = null;
        hoveredNodeRef.current = null;
        container.style.cursor = "default";
      }

      if (!node) {
        const edge = getIntersectedEdge(e);
        if (edge && edge !== hoveredEdgeLine) {
          // Reset previous hovered edge (only if it's not the selected or expansion path edge)
          if (hoveredEdgeLine) {
            const prevEdgeId = hoveredEdgeLine.userData.edgeId as string;
            const isSelected = prevEdgeId === selectedEdgeIdRef.current;
            if (!isSelected) {
              const mat = hoveredEdgeLine.material as THREE.LineBasicMaterial;
              if (expansionEdgeIds.has(prevEdgeId)) {
                mat.color.setHex(0x000000);
                mat.opacity = 1.0;
              } else {
                mat.color.setHex(EDGE_COLOR);
                mat.opacity = 0.6;
              }
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
          const hovEdgeId = hoveredEdgeLine.userData.edgeId as string;
          const isSelected = hovEdgeId === selectedEdgeIdRef.current;
          if (!isSelected) {
            const mat = hoveredEdgeLine.material as THREE.LineBasicMaterial;
            if (expansionEdgeIds.has(hovEdgeId)) {
              mat.color.setHex(0x000000);
              mat.opacity = 1.0;
            } else {
              mat.color.setHex(EDGE_COLOR);
              mat.opacity = 0.6;
            }
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
        const simN = meshToSimNode.get(hoveredNode);
        if (simN?.nodeSprite) {
          const ss = NODE_SPRITE_WORLD_SIZE * s;
          simN.nodeSprite.scale.set(ss, ss, 1);
        }
        hoveredNode = null;
        hoveredNodeRef.current = null;
        container.style.cursor = "default";
      }
      if (hoveredEdgeLine) {
        const leaveEdgeId = hoveredEdgeLine.userData.edgeId as string;
        const isSelected = leaveEdgeId === selectedEdgeIdRef.current;
        if (!isSelected) {
          const mat = hoveredEdgeLine.material as THREE.LineBasicMaterial;
          if (expansionEdgeIds.has(leaveEdgeId)) {
            mat.color.setHex(0x000000);
            mat.opacity = 1.0;
          } else {
            mat.color.setHex(EDGE_COLOR);
            mat.opacity = 0.6;
          }
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
            }, 300);
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
    const ANIM_SPEED = 0.018; // ~56 frames ≈ 930ms at 60fps
    const animate = () => {
      animId = requestAnimationFrame(animate);

      // Fade-in + scale-up animation for newly expanded nodes
      simNodes.forEach((node) => {
        if (node.animProgress < 1) {
          node.animProgress = Math.min(1, node.animProgress + ANIM_SPEED);
          const t = node.animProgress;
          const eased = t * (2 - t); // ease-out quadratic

          if (node.nodeSprite) {
            const targetScale = NODE_SPRITE_WORLD_SIZE * node.size;
            node.nodeSprite.scale.set(targetScale * eased, targetScale * eased, 1);
            const isDisabled = disabledNodeIdsRef.current.has(node.id);
            (node.nodeSprite.material as THREE.SpriteMaterial).opacity = (isDisabled ? 0.55 : 1.0) * eased;
          }
          if (node.mesh) {
            node.mesh.scale.set(node.size * eased, node.size * eased, 1);
          }
          if (node.labelSprite) {
            const isDisabled = disabledNodeIdsRef.current.has(node.id);
            (node.labelSprite.material as THREE.SpriteMaterial).opacity = (isDisabled ? 0.55 : 1.0) * eased;
          }
        }
      });

      simLinks.forEach((link) => {
        if (link.glowMesh) {
          const isHovered = hoveredEdgeLine !== null &&
            hoveredEdgeLine.userData.edgeId === link.id;
          const isSelected = link.id === selectedEdgeIdRef.current;
          const isExpansionPath = expansionEdgeIds.has(link.id);
          link.glowMesh.visible = isHovered || isSelected || isExpansionPath;
          if (isExpansionPath && !isSelected && !isHovered) {
            (link.glowMesh.material as THREE.MeshBasicMaterial).color.setHex(0x000000);
            (link.glowMesh.material as THREE.MeshBasicMaterial).opacity = 0.3;
          }
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
      // Dispose node sprites and labels (cached textures are preserved across renders)
      simNodes.forEach((node) => {
        if (node.nodeSprite) {
          (node.nodeSprite.material as THREE.SpriteMaterial).dispose();
        }
        if (node.labelSprite) {
          const mat = node.labelSprite.material as THREE.SpriteMaterial;
          mat.map?.dispose();
          mat.dispose();
        }
        if (node.mesh) {
          node.mesh.geometry.dispose();
          (node.mesh.material as THREE.MeshBasicMaterial).dispose();
        }
      });
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
