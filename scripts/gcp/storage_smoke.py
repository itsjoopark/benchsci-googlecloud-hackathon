#!/usr/bin/env python3
"""Smoke tests GCS permissions using ADC credentials.

Examples:
  python scripts/gcp/storage_smoke.py \
    --project-id benchspark-data-1771447466 \
    --bucket benchspark-data-1771447466-datasets \
    --mode read

  python scripts/gcp/storage_smoke.py \
    --project-id multihopwanderer-1771992134 \
    --bucket multihopwanderer-1771992134-team-bucket \
    --mode readwrite
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GCS ADC permission smoke test")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--mode", choices=["read", "readwrite"], required=True)
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional object prefix for listing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = storage.Client(project=args.project_id)
    bucket = client.bucket(args.bucket)

    try:
        blobs = list(client.list_blobs(bucket, prefix=args.prefix, max_results=5))
    except GoogleAPIError as exc:
        print(f"FAIL: cannot list objects in bucket '{args.bucket}': {exc}")
        return 1

    print(f"PASS: list objects in '{args.bucket}'")
    if blobs:
        print("Sample objects:")
        for blob in blobs[:5]:
            print(f"- {blob.name} ({blob.size} bytes)")
    else:
        print("Bucket appears empty or prefix matched no objects.")

    if args.mode == "read":
        print("PASS: read-only checks complete.")
        return 0

    test_name = (
        f"_codex_smoke/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}.txt"
    )
    blob = bucket.blob(test_name)
    payload = "gcs smoke test write/delete\n"

    try:
        blob.upload_from_string(payload, content_type="text/plain")
        print(f"PASS: upload succeeded: {test_name}")
    except GoogleAPIError as exc:
        print(f"FAIL: upload denied in '{args.bucket}': {exc}")
        return 1

    try:
        blob.delete()
        print(f"PASS: delete succeeded: {test_name}")
    except GoogleAPIError as exc:
        print(f"FAIL: delete denied in '{args.bucket}': {exc}")
        return 1

    print("PASS: read/write checks complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
