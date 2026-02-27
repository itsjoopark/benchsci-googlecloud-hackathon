#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="multihopwanderer-1771992134"
SERVICE_NAME="benchspark-backend"
REGION="us-central1"
OVERVIEW_API_KEY_SECRET="${OVERVIEW_API_KEY_SECRET:-overview-google-cloud-api-key}"
GEMINI_OVERVIEW_MODEL="${GEMINI_OVERVIEW_MODEL:-gemini-3-flash-preview}"
GEMINI_OVERVIEW_MODEL_FALLBACKS="${GEMINI_OVERVIEW_MODEL_FALLBACKS:-gemini-2.5-flash,gemini-2.0-flash-001}"
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
  local runtime_sa
  runtime_sa="$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

  if [[ -n "${runtime_sa}" ]]; then
    echo "Ensuring runtime SA can read secret ${OVERVIEW_API_KEY_SECRET}: ${runtime_sa}"
    gcloud secrets add-iam-policy-binding "${OVERVIEW_API_KEY_SECRET}" \
      --member="serviceAccount:${runtime_sa}" \
      --role="roles/secretmanager.secretAccessor" \
      --project="${PROJECT_ID}" \
      --quiet >/dev/null || true
  else
    echo "Runtime service account not found yet; skipping IAM binding pre-step."
  fi

  gcloud run deploy "${SERVICE_NAME}" \
    --source "${REPO_ROOT}/backend" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GEMINI_OVERVIEW_MODEL=${GEMINI_OVERVIEW_MODEL},GEMINI_OVERVIEW_MODEL_FALLBACKS=${GEMINI_OVERVIEW_MODEL_FALLBACKS}" \
    --set-secrets "GOOGLE_CLOUD_API_KEY=${OVERVIEW_API_KEY_SECRET}:latest"
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
