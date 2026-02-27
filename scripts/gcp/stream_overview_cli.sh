#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <request-json-file> [backend-base-url]"
  echo "Example: $0 /tmp/overview-edge.json http://localhost:8000"
  exit 1
fi

REQUEST_JSON="$1"
BACKEND_BASE_URL="${2:-http://localhost:8000}"

if [[ ! -f "$REQUEST_JSON" ]]; then
  echo "Request file not found: $REQUEST_JSON"
  exit 1
fi

ACCESS_TOKEN="$(gcloud auth print-access-token)"

echo "Streaming from ${BACKEND_BASE_URL}/api/overview/stream ..."
curl -N --http1.1 \
  -X POST "${BACKEND_BASE_URL}/api/overview/stream" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary "@${REQUEST_JSON}"
