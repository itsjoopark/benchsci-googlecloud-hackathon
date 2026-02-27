import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings

# Ensure google-auth picks up the service-account key for Vertex AI calls.
# pydantic-settings reads .env into Settings but does NOT set os.environ,
# so GOOGLE_APPLICATION_CREDENTIALS must be set explicitly.
_sa_key = Path(settings.SERVICE_ACCOUNT_KEY_PATH)
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and _sa_key.exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_sa_key.resolve())

from backend.routers.query import router as query_router
from backend.routers.snapshot import router as snapshot_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BioRender API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(snapshot_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
