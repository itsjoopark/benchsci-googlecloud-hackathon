#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-multihopwanderer-1771992134}"
REGION="${GCP_REGION:-us-central1}"
MODEL_ID="${GEMINI_OVERVIEW_MODEL:-gemini-3-flash-preview}"
PROMPT="${1:-Explain why BRCA1 is connected to breast cancer in biomedical knowledge graphs. Cite evidence IDs explicitly.}"

TOKEN="$(gcloud auth print-access-token)"

cat <<EOF >/tmp/vertex-overview-request.json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {"text": ${PROMPT@Q}}
      ]
    }
  ],
  "generationConfig": {
    "temperature": 0.2,
    "maxOutputTokens": 600,
    "topP": 0.9
  }
}
EOF

URL="https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/publishers/google/models/${MODEL_ID}:streamGenerateContent"

echo "Calling ${MODEL_ID} on Vertex in ${REGION} ..."
curl -sS -N \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST "${URL}" \
  --data-binary @/tmp/vertex-overview-request.json
