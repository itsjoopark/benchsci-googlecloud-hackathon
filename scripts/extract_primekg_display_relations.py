#!/usr/bin/env python3
"""One-time script to extract distinct display_relation mappings from PrimeKG in BigQuery.

Usage:
    source scripts/gcp/switch-config.sh && use_multihop
    python scripts/extract_primekg_display_relations.py

Outputs a table of (relation, display_relation, x_type, y_type) that can be used
to validate and extend RELATION_TYPE_TO_DISPLAY_LABEL in backend/mappings.py.
"""

from google.cloud import bigquery

PROJECT = "multihopwanderer-1771992134"
QUERY = """
SELECT DISTINCT
    relation,
    display_relation,
    x_type,
    y_type
FROM `multihopwanderer-1771992134.primekg.primekg`
ORDER BY x_type, y_type, display_relation
"""


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    print("Querying PrimeKG for distinct display_relation mappings...\n")
    rows = client.query(QUERY).result()

    print(f"{'relation':<30} {'display_relation':<30} {'x_type':<15} {'y_type':<15}")
    print("-" * 90)
    for row in rows:
        print(
            f"{row.relation:<30} {row.display_relation:<30} "
            f"{row.x_type:<15} {row.y_type:<15}"
        )


if __name__ == "__main__":
    main()
