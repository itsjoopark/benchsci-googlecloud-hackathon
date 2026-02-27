#!/usr/bin/env python3
"""Migrate entities and relationships from BigQuery (pubmed_kg) to Cloud Spanner.

Usage:
    python scripts/gcp/load_spanner_graph.py

Requires:
    - google-cloud-bigquery
    - google-cloud-spanner
    - Authenticated gcloud credentials (or GOOGLE_APPLICATION_CREDENTIALS)
"""

import sys
import time
from pathlib import Path
from google.cloud import bigquery, spanner
from google.oauth2 import service_account

PROJECT_ID = "multihopwanderer-1771992134"
BQ_DATASET = "pubmed_kg"
SPANNER_INSTANCE = "benchspark-graph"
SPANNER_DATABASE = "biograph"
BATCH_SIZE = 500  # Spanner mutation limit per commit
SERVICE_ACCOUNT_KEY = "service-account-key.json"


def extract_entities(bq_client: bigquery.Client) -> list[tuple]:
    """Extract distinct entities from BigQuery."""
    sql = f"""
    SELECT DISTINCT EntityId, Type, Mention
    FROM `{PROJECT_ID}.{BQ_DATASET}.C23_BioEntities`
    WHERE EntityId IS NOT NULL
    """
    print("Querying entities from BigQuery...")
    rows = list(bq_client.query(sql).result())
    print(f"  Found {len(rows)} entities.")
    return [(row["EntityId"], row["Type"], row["Mention"]) for row in rows]


def extract_relationships(bq_client: bigquery.Client) -> list[tuple]:
    """Extract deduplicated relationships from BigQuery."""
    sql = f"""
    SELECT DISTINCT entity_id1, entity_id2, relation_type
    FROM `{PROJECT_ID}.{BQ_DATASET}.C21_Bioentity_Relationships`
    WHERE entity_id1 IS NOT NULL AND entity_id2 IS NOT NULL
      AND relation_type IS NOT NULL
    """
    print("Querying relationships from BigQuery...")
    rows = list(bq_client.query(sql).result())
    print(f"  Found {len(rows)} unique relationships.")
    return [(row["entity_id1"], row["entity_id2"], row["relation_type"]) for row in rows]


def batch_insert(database, table: str, columns: list[str], rows: list[tuple]):
    """Insert rows into Spanner in batches."""
    total = len(rows)
    inserted = 0

    for i in range(0, total, BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        with database.batch() as batch:
            batch.insert(table=table, columns=columns, values=chunk)
        inserted += len(chunk)
        if inserted % 5000 == 0 or inserted == total:
            print(f"  {table}: {inserted}/{total} rows inserted")


def _get_credentials():
    """Load service account credentials if key file exists."""
    sa_path = Path(SERVICE_ACCOUNT_KEY)
    if sa_path.exists():
        print(f"Using service account key: {sa_path}")
        return service_account.Credentials.from_service_account_file(str(sa_path))
    print("No service account key found, using Application Default Credentials.")
    return None


def main():
    creds = _get_credentials()
    bq_kwargs = {"project": PROJECT_ID}
    sp_kwargs = {"project": PROJECT_ID}
    if creds:
        bq_kwargs["credentials"] = creds
        sp_kwargs["credentials"] = creds.with_scopes(
            ["https://www.googleapis.com/auth/spanner.data"]
        )
    bq_client = bigquery.Client(**bq_kwargs)
    spanner_client = spanner.Client(**sp_kwargs)
    instance = spanner_client.instance(SPANNER_INSTANCE)
    database = instance.database(SPANNER_DATABASE)

    # Step 1: Entities (must be inserted first — foreign key constraint)
    entities = extract_entities(bq_client)
    print(f"\nInserting {len(entities)} entities into Spanner BioEntity...")
    t0 = time.time()
    batch_insert(database, "BioEntity", ["entity_id", "entity_type", "mention"], entities)
    print(f"  Entities done in {time.time() - t0:.1f}s")

    # Step 2: Relationships
    relationships = extract_relationships(bq_client)
    print(f"\nInserting {len(relationships)} relationships into Spanner BioRelationship...")
    t0 = time.time()
    batch_insert(
        database,
        "BioRelationship",
        ["entity_id1", "entity_id2", "relation_type"],
        relationships,
    )
    print(f"  Relationships done in {time.time() - t0:.1f}s")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
