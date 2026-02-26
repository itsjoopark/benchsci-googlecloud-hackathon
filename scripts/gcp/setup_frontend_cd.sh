#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-multihopwanderer-1771992134}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-benchspark-frontend}"
AR_REPO="${AR_REPO:-cloud-run-source-deploy}"
TRIGGER_NAME="${TRIGGER_NAME:-benchspark-frontend-main}"
GITHUB_OWNER="${GITHUB_OWNER:-itsjoopark}"
GITHUB_REPO="${GITHUB_REPO:-benchsci-googlecloud-hackathon}"
BRANCH_PATTERN="${BRANCH_PATTERN:-^main$}"
TRIGGER_DESC="${TRIGGER_DESC:-Deploy frontend to Cloud Run on main push}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
RUNTIME_SA="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(spec.template.spec.serviceAccountName)')"

echo "Project: ${PROJECT_ID} (${PROJECT_NUMBER})"
echo "Cloud Build SA: ${CLOUDBUILD_SA}"
echo "Runtime SA: ${RUNTIME_SA}"
echo "Trigger: ${TRIGGER_NAME}"

errors=0

try_or_report() {
  local message="$1"
  shift
  echo "${message}"
  if ! "$@"; then
    errors=1
  fi
}

if ! gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Creating Artifact Registry repo ${AR_REPO} in ${REGION}"
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --description="Container images for Cloud Run deploys"
fi

echo "Granting IAM roles to Cloud Build service account"
try_or_report "Applying roles/run.admin on project to ${CLOUDBUILD_SA}" \
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin" \
  --quiet

try_or_report "Applying roles/artifactregistry.writer on project to ${CLOUDBUILD_SA}" \
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer" \
  --quiet

try_or_report "Applying roles/iam.serviceAccountUser on runtime SA ${RUNTIME_SA} to ${CLOUDBUILD_SA}" \
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}" \
  --quiet

if gcloud builds triggers list --project="${PROJECT_ID}" --format='value(name)' | rg -x "${TRIGGER_NAME}" >/dev/null 2>&1; then
  echo "Trigger ${TRIGGER_NAME} already exists; skipping create."
else
  echo "Creating trigger ${TRIGGER_NAME}"
  if ! gcloud builds triggers create github \
    --project="${PROJECT_ID}" \
    --name="${TRIGGER_NAME}" \
    --description="${TRIGGER_DESC}" \
    --repo-owner="${GITHUB_OWNER}" \
    --repo-name="${GITHUB_REPO}" \
    --branch-pattern="${BRANCH_PATTERN}" \
    --build-config="cloudbuild.yaml" \
    --region="${REGION}" \
    --include-logs-with-status \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${CLOUDBUILD_SA}"; then
    errors=1
  fi
fi

if [[ "${errors}" -ne 0 ]]; then
  cat <<EOF

Setup finished with errors.

Common fixes:
1) If IAM binding failed, run this script with a project IAM admin account.
2) If trigger creation failed with repository mapping error, connect GitHub repo first:
   https://console.cloud.google.com/cloud-build/triggers;region=${REGION}/connect?project=${PROJECT_NUMBER}
EOF
  exit 1
fi

echo "CD setup complete."
