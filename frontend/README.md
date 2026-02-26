# Frontend Deployment (Cloud Run)

This frontend is a Vite + React + TypeScript + Three.js app.

## Build behavior

- `npm run build` performs strict TypeScript build (`tsc -b && vite build`) and currently fails due known TS issues.
- `npm run build:deploy` runs `vite build` only and is used for Docker/Cloud Run deployment.

## Local run

```bash
cd frontend
npm ci
npm run dev
```

## Local Docker validation

From repo root:

```bash
docker build -t benchspark-frontend:local frontend
docker run --rm -p 8080:8080 benchspark-frontend:local
```

Then open `http://localhost:8080`.

## Deploy to Cloud Run (`us-central1`)

Service name: `benchspark-frontend`
Project: `multihopwanderer-1771992134`

Use the script from repo root:

```bash
./scripts/gcp/deploy_frontend_cloud_run.sh
```

Or run manually:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/kezit/Repositories/benchsci-googlecloud-hackathon/multihopwanderer-1771992134-e47e99e17b16.json"
gcloud auth activate-service-account --key-file="$GOOGLE_APPLICATION_CREDENTIALS"
gcloud config set project multihopwanderer-1771992134

gcloud run deploy benchspark-frontend \
  --source frontend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

If IAM is denied with the App Engine key, retry with:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/kezit/Repositories/benchsci-googlecloud-hackathon/multihopwanderer-1771992134-adeeefb1ffe1.json"
```

Then rerun the same deploy command.

## Simple CD pipeline (Cloud Build -> Cloud Run)

This repo includes a root-level Cloud Build pipeline at
`/Users/kezit/Repositories/benchsci-googlecloud-hackathon/cloudbuild.yaml`.

It does:

- Docker build from `frontend/`
- Push image to Artifact Registry
- Deploy image to Cloud Run service `benchspark-frontend`

One-time setup from repo root:

```bash
gcloud config set account kezitogaleacurmi@gmail.com
gcloud config set project multihopwanderer-1771992134
./scripts/gcp/setup_frontend_cd.sh
```

After setup, every push to `main` triggers deploy automatically.

If setup fails, complete these prerequisites:

1. Connect the GitHub repo to Cloud Build in this project:
   - <https://console.cloud.google.com/cloud-build/triggers;region=us-central1/connect?project=113940992739>
2. Run setup with a principal that can update IAM policy (`setIamPolicy`) on project/service accounts.
