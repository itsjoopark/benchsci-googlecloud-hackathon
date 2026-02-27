#!/usr/bin/env bash
# setup_spanner_graph.sh — Create Cloud Spanner instance, database, and graph schema.
#
# Usage:
#   source scripts/gcp/switch-config.sh && use_multihop
#   bash scripts/gcp/setup_spanner_graph.sh
#
set -euo pipefail

PROJECT_ID="multihopwanderer-1771992134"
INSTANCE_ID="benchspark-graph"
DATABASE_ID="biograph"
CONFIG="regional-us-central1"

echo "==> Creating Spanner instance '${INSTANCE_ID}' (config=${CONFIG})..."
gcloud spanner instances create "${INSTANCE_ID}" \
  --project="${PROJECT_ID}" \
  --config="${CONFIG}" \
  --edition=ENTERPRISE \
  --description="BioRender knowledge graph" \
  --processing-units=300 \
  || echo "Instance may already exist — continuing."

echo "==> Creating database '${DATABASE_ID}'..."
gcloud spanner databases create "${DATABASE_ID}" \
  --project="${PROJECT_ID}" \
  --instance="${INSTANCE_ID}" \
  || echo "Database may already exist — continuing."

echo "==> Applying DDL (node table, edge table, property graph)..."
gcloud spanner databases ddl update "${DATABASE_ID}" \
  --project="${PROJECT_ID}" \
  --instance="${INSTANCE_ID}" \
  --ddl="
CREATE TABLE BioEntity (
  entity_id STRING(MAX) NOT NULL,
  entity_type STRING(64),
  mention STRING(MAX),
) PRIMARY KEY (entity_id);

CREATE TABLE BioRelationship (
  entity_id1 STRING(MAX) NOT NULL,
  entity_id2 STRING(MAX) NOT NULL,
  relation_type STRING(128) NOT NULL,
  FOREIGN KEY (entity_id1) REFERENCES BioEntity (entity_id),
  FOREIGN KEY (entity_id2) REFERENCES BioEntity (entity_id),
) PRIMARY KEY (entity_id1, entity_id2, relation_type);

CREATE INDEX BioRelationship_Reverse
  ON BioRelationship (entity_id2, entity_id1, relation_type);

CREATE OR REPLACE PROPERTY GRAPH BioGraph
  NODE TABLES (BioEntity)
  EDGE TABLES (
    BioRelationship
      SOURCE KEY (entity_id1) REFERENCES BioEntity (entity_id)
      DESTINATION KEY (entity_id2) REFERENCES BioEntity (entity_id)
      LABEL Relationship
  );
"

echo "==> Done. Verify with:"
echo "  gcloud spanner databases execute-sql ${DATABASE_ID} \\"
echo "    --instance=${INSTANCE_ID} --project=${PROJECT_ID} \\"
echo "    --sql=\"SELECT COUNT(*) FROM BioEntity\""
