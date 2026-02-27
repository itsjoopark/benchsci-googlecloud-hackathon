# BenchSci Google Cloud Hackathon

Monorepo with separate Cloud Run services:

- Frontend: `frontend/` (`benchspark-frontend`)
- Backend: `backend/` (`benchspark-backend`)

## Manual deploy scripts

From repo root:

```bash
./scripts/gcp/deploy_frontend_cloud_run.sh
./scripts/gcp/deploy_backend_cloud_run.sh
```

## Monorepo CD

Cloud Build configs:

- `cloudbuild.frontend.yaml` (build/deploy frontend)
- `cloudbuild.backend.yaml` (build/deploy backend)
- `cloudbuild.yaml` (alias to frontend pipeline)

One-time setup script:

```bash
./scripts/gcp/setup_monorepo_cd.sh
```

It creates two `main` branch triggers with folder filters:

- Frontend trigger includes: `frontend/**`, `cloudbuild.frontend.yaml`, `cloudbuild.yaml`
- Backend trigger includes: `backend/**`, `cloudbuild.backend.yaml`
