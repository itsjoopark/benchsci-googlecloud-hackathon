#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="multihopwanderer-1771992134"
SERVICE_NAME="benchspark-frontend"
REGION="us-central1"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

KEY_PRIMARY="${REPO_ROOT}/multihopwanderer-1771992134-e47e99e17b16.json"
KEY_FALLBACK="${REPO_ROOT}/multihopwanderer-1771992134-adeeefb1ffe1.json"

if [[ ! -f "${KEY_PRIMARY}" ]]; then
  echo "Primary key file not found: ${KEY_PRIMARY}" >&2
  exit 1
fi

activate_key() {
  local key_file="$1"
  export GOOGLE_APPLICATION_CREDENTIALS="${key_file}"
  echo "Activating service account key: ${key_file}"
  gcloud auth activate-service-account --key-file="${GOOGLE_APPLICATION_CREDENTIALS}" >/dev/null
  gcloud config set project "${PROJECT_ID}" >/dev/null
}

deploy() {
  gcloud run deploy "${SERVICE_NAME}" \
    --source "${REPO_ROOT}/frontend" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated
}

activate_key "${KEY_PRIMARY}"
if ! deploy; then
  if [[ ! -f "${KEY_FALLBACK}" ]]; then
    echo "Deploy failed and fallback key file is missing: ${KEY_FALLBACK}" >&2
    exit 1
  fi
  echo "Primary key deploy failed; retrying with fallback key."
  activate_key "${KEY_FALLBACK}"
  deploy
fi

echo "Deployment finished for ${SERVICE_NAME} in ${PROJECT_ID}/${REGION}."
