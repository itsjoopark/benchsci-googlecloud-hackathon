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

## Current live URL

- Canonical URL from Cloud Run status: `https://benchspark-backend-s7fuxsjnxq-uc.a.run.app`
- Health check: `GET /health`
