# Backend Deployment (Cloud Run)

FastAPI service in this monorepo, deployed as Cloud Run service `benchspark-backend` in `us-central1`.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
```

## Docker

```bash
docker build -t benchspark-backend:local backend
docker run --rm -p 8080:8080 benchspark-backend:local
```

Health endpoint:

```bash
curl http://localhost:8080/health
```

## Deploy to Cloud Run

From repo root:

```bash
./scripts/gcp/deploy_backend_cloud_run.sh
```

This uses root service-account JSON keys with fallback and deploys from `backend/` source.
It also maps Secret Manager secret `overview-google-cloud-api-key` to
`GOOGLE_CLOUD_API_KEY` on Cloud Run at deploy time.

Optional overrides:

```bash
OVERVIEW_API_KEY_SECRET=your-secret-name \
GEMINI_OVERVIEW_MODEL=gemini-3-flash-preview \
GEMINI_OVERVIEW_MODEL_FALLBACKS=gemini-2.5-flash,gemini-2.0-flash-001 \
./scripts/gcp/deploy_backend_cloud_run.sh
```

## Current live URL

- Canonical URL from Cloud Run status: `https://benchspark-backend-s7fuxsjnxq-uc.a.run.app`
- Health check: `GET /health`
