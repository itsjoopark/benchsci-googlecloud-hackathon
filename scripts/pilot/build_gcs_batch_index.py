#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

from pilot_rag.gcs_index_pipeline import GCSBatchIndexBuilder
from pilot_rag.config import SETTINGS


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Vertex Vector Search batch index from GCS datapoints.")
    parser.add_argument("--bucket", required=True, help="GCS bucket for datapoints, e.g. multihopwanderer-...-team-bucket")
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot", help="Run mode")
    parser.add_argument("--limit", type=int, default=500, help="Doc limit (0 means uncapped for full mode)")
    parser.add_argument("--batch-docs", type=int, default=10000, help="Docs per shard")
    parser.add_argument("--workers", type=int, default=2, help="Parallel embedding workers")
    parser.add_argument("--max-retries", type=int, default=6, help="Max retries per embedding batch")
    parser.add_argument("--min-linked-entities", type=int, default=2, help="Minimum distinct linked entities per doc")
    parser.add_argument("--no-type-filter", dest="no_type_filter", action="store_true", help="Disable entity type filtering")
    parser.add_argument("--type-filter", dest="no_type_filter", action="store_false", help="Enable entity type filtering")
    parser.add_argument("--resume-run-id", default=None, help="Resume a previous run id")
    parser.add_argument("--dry-run", action="store_true", help="Build metadata only, no embedding/index")
    parser.add_argument("--skip-index", action="store_true", help="Skip index creation after datapoints upload")
    parser.add_argument("--prefix", default=None, help="Optional GCS prefix under bucket")
    parser.set_defaults(no_type_filter=True)
    args = parser.parse_args()

    builder = GCSBatchIndexBuilder(bucket_name=args.bucket, prefix=args.prefix, run_id=args.resume_run_id)
    allowed_types = [t.strip().lower() for t in SETTINGS.allowed_entity_types_csv.split(",") if t.strip()]
    result = builder.build(
        mode=args.mode,
        limit=args.limit,
        batch_docs=args.batch_docs,
        workers=args.workers,
        max_retries=args.max_retries,
        min_linked_entities=args.min_linked_entities,
        enable_entity_type_filter=not args.no_type_filter,
        allowed_entity_types=allowed_types,
        resume_run_id=args.resume_run_id,
        dry_run=args.dry_run,
        skip_index=args.skip_index,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
