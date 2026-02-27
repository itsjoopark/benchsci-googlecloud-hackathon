import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers.query import router as query_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BioRender API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
