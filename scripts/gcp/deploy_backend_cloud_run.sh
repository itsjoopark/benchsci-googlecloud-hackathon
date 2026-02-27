#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="multihopwanderer-1771992134"
SERVICE_NAME="benchspark-backend"
REGION="us-central1"
OVERVIEW_API_KEY_SECRET="${OVERVIEW_API_KEY_SECRET:-GEMINI_API_KEY}"
EXTRACTION_APP_KEY_SECRET="${EXTRACTION_APP_KEY_SECRET:-GEMINI_APP_KEY}"
GEMINI_OVERVIEW_MODEL="${GEMINI_OVERVIEW_MODEL:-gemini-3-flash-preview}"
GEMINI_OVERVIEW_MODEL_FALLBACKS="${GEMINI_OVERVIEW_MODEL_FALLBACKS:-gemini-2.5-flash,gemini-2.0-flash-001}"
USE_ACTIVE_GCLOUD_ACCOUNT="${USE_ACTIVE_GCLOUD_ACCOUNT:-false}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

KEY_PRIMARY="${REPO_ROOT}/multihopwanderer-1771992134-e47e99e17b16.json"
KEY_FALLBACK="${REPO_ROOT}/multihopwanderer-1771992134-adeeefb1ffe1.json"

activate_key() {
  local key_file="$1"
  export GOOGLE_APPLICATION_CREDENTIALS="${key_file}"
  echo "Activating service account key: ${key_file}"
  gcloud auth activate-service-account --key-file="${GOOGLE_APPLICATION_CREDENTIALS}" >/dev/null
  gcloud config set project "${PROJECT_ID}" >/dev/null
}

deploy() {
  local runtime_sa
  local overview_secret_exists=0
  local extraction_secret_exists=0
  local secret_mappings=()
  local env_vars
  runtime_sa="$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

  if gcloud secrets describe "${OVERVIEW_API_KEY_SECRET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    overview_secret_exists=1
    secret_mappings+=("GOOGLE_CLOUD_API_KEY=${OVERVIEW_API_KEY_SECRET}:latest")
    secret_mappings+=("GEMINI_API_KEY=${OVERVIEW_API_KEY_SECRET}:latest")
  fi

  if gcloud secrets describe "${EXTRACTION_APP_KEY_SECRET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    extraction_secret_exists=1
    secret_mappings+=("GEMINI_APP_KEY=${EXTRACTION_APP_KEY_SECRET}:latest")
  fi

  if [[ -n "${runtime_sa}" ]]; then
    local secret_name
    for secret_name in "${OVERVIEW_API_KEY_SECRET}" "${EXTRACTION_APP_KEY_SECRET}"; do
      if gcloud secrets describe "${secret_name}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
        echo "Ensuring runtime SA can read secret ${secret_name}: ${runtime_sa}"
        if ! gcloud secrets add-iam-policy-binding "${secret_name}" \
          --member="serviceAccount:${runtime_sa}" \
          --role="roles/secretmanager.secretAccessor" \
          --project="${PROJECT_ID}" \
          --quiet >/dev/null; then
          echo "Warning: failed to set secret IAM binding for ${secret_name}. Use an admin account or run with USE_ACTIVE_GCLOUD_ACCOUNT=true." >&2
        fi
      fi
    done
  else
    echo "Runtime service account not found yet; skipping IAM binding pre-step."
  fi

  if [[ "${overview_secret_exists}" -eq 0 ]]; then
    echo "Secret ${OVERVIEW_API_KEY_SECRET} not found; overview stream may fail."
  fi

  if [[ "${extraction_secret_exists}" -eq 0 ]]; then
    echo "Secret ${EXTRACTION_APP_KEY_SECRET} not found; /api/query extraction will fail." >&2
    echo "Create it with the Vertex AI Studio app key from Manage App, then redeploy." >&2
    return 1
  fi

  env_vars="^##^GCP_PROJECT_ID=${PROJECT_ID}##GCP_REGION=${REGION}##GEMINI_OVERVIEW_MODEL=${GEMINI_OVERVIEW_MODEL}##GEMINI_OVERVIEW_MODEL_FALLBACKS=${GEMINI_OVERVIEW_MODEL_FALLBACKS}"

  if [[ "${#secret_mappings[@]}" -gt 0 ]]; then
    local joined_secrets=""
    local mapping
    for mapping in "${secret_mappings[@]}"; do
      if [[ -z "${joined_secrets}" ]]; then
        joined_secrets="${mapping}"
      else
        joined_secrets="${joined_secrets},${mapping}"
      fi
    done
    gcloud run deploy "${SERVICE_NAME}" \
      --source "${REPO_ROOT}/backend" \
      --region "${REGION}" \
      --platform managed \
      --allow-unauthenticated \
      --set-env-vars "${env_vars}" \
      --set-secrets "${joined_secrets}"
    return
  fi

  gcloud run deploy "${SERVICE_NAME}" \
    --source "${REPO_ROOT}/backend" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "${env_vars}"
}

if [[ "${USE_ACTIVE_GCLOUD_ACCOUNT}" == "true" ]]; then
  echo "Using active gcloud account for deployment and IAM operations."
  gcloud config set project "${PROJECT_ID}" >/dev/null
  deploy
else
  if [[ ! -f "${KEY_PRIMARY}" ]]; then
    echo "Primary key file not found: ${KEY_PRIMARY}" >&2
    exit 1
  fi

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
fi

echo "Deployment finished for ${SERVICE_NAME} in ${PROJECT_ID}/${REGION}."
