import type { Entity, GraphEdge, EntityType } from "../types";

export interface RankingContext {
  candidates: Entity[];
  edges: GraphEdge[];
  existingEntities: Entity[];
  maxResults: number;
}

// Weights for each signal in the composite score
const W_CONFIDENCE = 0.35;
const W_EVIDENCE = 0.25;
const W_PROVENANCE = 0.15;
const W_PUBLICATION = 0.15;
const W_COOCCURRENCE = 0.10;

// Normalization caps
const EVIDENCE_CAP = 10;
const PUBLICATION_CAP = 20;

const PROVENANCE_VALUES: Record<string, number> = {
  curated: 1.0,
  literature: 0.5,
  inferred: 0.2,
};

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function getConnectingEdges(
  candidateId: string,
  edges: GraphEdge[],
  visibleIds: Set<string>,
): GraphEdge[] {
  return edges.filter(
    (e) =>
      (e.source === candidateId && visibleIds.has(e.target)) ||
      (e.target === candidateId && visibleIds.has(e.source)),
  );
}

export function computeCompositeScore(
  candidateId: string,
  edges: GraphEdge[],
  visibleIds: Set<string>,
): number {
  const connecting = getConnectingEdges(candidateId, edges, visibleIds);
  if (connecting.length === 0) return 0;

  // A. Aggregated confidence: mean + edge-count bonus
  const scores = connecting.map((e) => e.score ?? 0);
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const edgeBonus = 0.1 * Math.log2(connecting.length);
  const confidence = clamp01(mean + edgeBonus);

  // B. Evidence count across all connecting edges
  const totalEvidence = connecting.reduce(
    (sum, e) => sum + (e.evidence?.length ?? 0),
    0,
  );
  const evidenceSignal = Math.min(totalEvidence / EVIDENCE_CAP, 1);

  // C. Provenance quality: best among connecting edges
  const provenanceSignal = Math.max(
    ...connecting.map((e) => PROVENANCE_VALUES[e.provenance] ?? 0.2),
  );

  // D. Publication metrics: papers + trials*3 + patents*2
  const pubTotal = connecting.reduce((sum, e) => {
    return (
      sum +
      (e.paperCount ?? 0) +
      (e.trialCount ?? 0) * 3 +
      (e.patentCount ?? 0) * 2
    );
  }, 0);
  const publicationSignal = Math.min(pubTotal / PUBLICATION_CAP, 1);

  // E. Co-occurrence: max across connecting edges
  const cooccurrenceSignal = clamp01(
    Math.max(...connecting.map((e) => e.cooccurrenceScore ?? 0)),
  );

  return (
    confidence * W_CONFIDENCE +
    evidenceSignal * W_EVIDENCE +
    provenanceSignal * W_PROVENANCE +
    publicationSignal * W_PUBLICATION +
    cooccurrenceSignal * W_COOCCURRENCE
  );
}

function diverseSelect(
  scored: Array<{ entity: Entity; score: number }>,
  maxResults: number,
): Entity[] {
  if (scored.length <= maxResults) {
    return scored.map((s) => s.entity);
  }

  const sorted = [...scored].sort((a, b) => b.score - a.score);

  // Group by type, preserving within-group score order
  const byType = new Map<EntityType, typeof sorted>();
  for (const item of sorted) {
    const t = item.entity.type;
    if (!byType.has(t)) byType.set(t, []);
    byType.get(t)!.push(item);
  }

  const result: Entity[] = [];
  const used = new Set<string>();

  // Phase 1: one best representative from each type
  for (const [, group] of byType) {
    if (result.length >= maxResults) break;
    const best = group[0];
    result.push(best.entity);
    used.add(best.entity.id);
  }

  // Phase 2: fill remaining slots from globally sorted list
  for (const item of sorted) {
    if (result.length >= maxResults) break;
    if (!used.has(item.entity.id)) {
      result.push(item.entity);
      used.add(item.entity.id);
    }
  }

  return result;
}

/**
 * Rank expansion candidates using a composite score (confidence, evidence,
 * provenance, publication metrics, co-occurrence) and ensure entity-type
 * diversity in the results.
 */
export function rankCandidates(ctx: RankingContext): Entity[] {
  const { candidates, edges, existingEntities, maxResults } = ctx;
  if (candidates.length <= maxResults) return candidates;

  const visibleIds = new Set(existingEntities.map((e) => e.id));

  const scored = candidates.map((entity) => ({
    entity,
    score: computeCompositeScore(entity.id, edges, visibleIds),
  }));

  return diverseSelect(scored, maxResults);
}
