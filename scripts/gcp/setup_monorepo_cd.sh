#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-multihopwanderer-1771992134}"
REGION="${REGION:-us-central1}"
AR_REPO="${AR_REPO:-cloud-run-source-deploy}"
GITHUB_OWNER="${GITHUB_OWNER:-itsjoopark}"
GITHUB_REPO="${GITHUB_REPO:-benchsci-googlecloud-hackathon}"
BRANCH_PATTERN="${BRANCH_PATTERN:-^main$}"

FRONTEND_SERVICE="${FRONTEND_SERVICE:-benchspark-frontend}"
BACKEND_SERVICE="${BACKEND_SERVICE:-benchspark-backend}"
FRONTEND_TRIGGER="${FRONTEND_TRIGGER:-benchspark-frontend-main}"
BACKEND_TRIGGER="${BACKEND_TRIGGER:-benchspark-backend-main}"
OVERVIEW_API_KEY_SECRET="${OVERVIEW_API_KEY_SECRET:-overview-google-cloud-api-key}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
FRONTEND_RUNTIME_SA="$(gcloud run services describe "${FRONTEND_SERVICE}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
BACKEND_RUNTIME_SA="$(gcloud run services describe "${BACKEND_SERVICE}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

echo "Project: ${PROJECT_ID} (${PROJECT_NUMBER})"
echo "Cloud Build SA: ${CLOUDBUILD_SA}"

action_failed=0

run_or_flag() {
  local label="$1"
  shift
  echo "${label}"
  if ! "$@"; then
    action_failed=1
  fi
}

if ! gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  run_or_flag "Creating Artifact Registry repo ${AR_REPO}" \
    gcloud artifacts repositories create "${AR_REPO}" \
      --repository-format=docker \
      --location="${REGION}" \
      --project="${PROJECT_ID}" \
      --description="Container images for monorepo Cloud Run deploys"
fi

run_or_flag "Grant roles/run.admin to Cloud Build SA" \
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="roles/run.admin" \
    --quiet

run_or_flag "Grant roles/artifactregistry.writer to Cloud Build SA" \
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="roles/artifactregistry.writer" \
    --quiet

if [[ -n "${FRONTEND_RUNTIME_SA}" ]]; then
  run_or_flag "Grant roles/iam.serviceAccountUser on frontend runtime SA" \
    gcloud iam service-accounts add-iam-policy-binding "${FRONTEND_RUNTIME_SA}" \
      --member="serviceAccount:${CLOUDBUILD_SA}" \
      --role="roles/iam.serviceAccountUser" \
      --project="${PROJECT_ID}" \
      --quiet
fi

if [[ -n "${BACKEND_RUNTIME_SA}" ]]; then
  run_or_flag "Grant roles/iam.serviceAccountUser on backend runtime SA" \
    gcloud iam service-accounts add-iam-policy-binding "${BACKEND_RUNTIME_SA}" \
      --member="serviceAccount:${CLOUDBUILD_SA}" \
      --role="roles/iam.serviceAccountUser" \
      --project="${PROJECT_ID}" \
      --quiet

  if gcloud secrets describe "${OVERVIEW_API_KEY_SECRET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    run_or_flag "Grant roles/secretmanager.secretAccessor on ${OVERVIEW_API_KEY_SECRET} to backend runtime SA" \
      gcloud secrets add-iam-policy-binding "${OVERVIEW_API_KEY_SECRET}" \
        --member="serviceAccount:${BACKEND_RUNTIME_SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}" \
        --quiet
  else
    echo "Secret ${OVERVIEW_API_KEY_SECRET} not found; skipping backend runtime secret binding."
  fi
fi

if gcloud builds triggers list --project="${PROJECT_ID}" --region="${REGION}" --format='value(name)' | rg -x "${FRONTEND_TRIGGER}" >/dev/null 2>&1; then
  echo "Trigger ${FRONTEND_TRIGGER} already exists"
else
  run_or_flag "Creating frontend trigger ${FRONTEND_TRIGGER}" \
    gcloud builds triggers create github \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --name="${FRONTEND_TRIGGER}" \
      --description="Deploy frontend on main changes" \
      --repo-owner="${GITHUB_OWNER}" \
      --repo-name="${GITHUB_REPO}" \
      --branch-pattern="${BRANCH_PATTERN}" \
      --build-config="cloudbuild.frontend.yaml" \
      --included-files="frontend/**,cloudbuild.frontend.yaml,cloudbuild.yaml" \
      --service-account="projects/${PROJECT_ID}/serviceAccounts/${CLOUDBUILD_SA}" \
      --include-logs-with-status
fi

if gcloud builds triggers list --project="${PROJECT_ID}" --region="${REGION}" --format='value(name)' | rg -x "${BACKEND_TRIGGER}" >/dev/null 2>&1; then
  echo "Trigger ${BACKEND_TRIGGER} already exists"
else
  run_or_flag "Creating backend trigger ${BACKEND_TRIGGER}" \
    gcloud builds triggers create github \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --name="${BACKEND_TRIGGER}" \
      --description="Deploy backend on main changes" \
      --repo-owner="${GITHUB_OWNER}" \
      --repo-name="${GITHUB_REPO}" \
      --branch-pattern="${BRANCH_PATTERN}" \
      --build-config="cloudbuild.backend.yaml" \
      --included-files="backend/**,cloudbuild.backend.yaml" \
      --service-account="projects/${PROJECT_ID}/serviceAccounts/${CLOUDBUILD_SA}" \
      --include-logs-with-status
fi

if [[ "${action_failed}" -ne 0 ]]; then
  cat <<MSG

Monorepo CD setup completed with errors.

Likely prerequisites:
1) Run with a principal that can update IAM policy in ${PROJECT_ID}.
2) Connect GitHub repository mapping first:
   https://console.cloud.google.com/cloud-build/triggers;region=${REGION}/connect?project=${PROJECT_NUMBER}
MSG
  exit 1
fi

echo "Monorepo CD setup complete."
