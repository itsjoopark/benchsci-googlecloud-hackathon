from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GCP_PROJECT_ID: str = "multihopwanderer-1771992134"
    GCP_REGION: str = "us-central1"
    GEMINI_ENDPOINT_URL: str = "https://genai-app-entityextraction-1-1772149446997-113940992739.us-central1.run.app/"
    GEMINI_APP_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GOOGLE_CLOUD_API_KEY: str = ""
    GEMINI_OVERVIEW_MODEL: str = "gemini-3-flash-preview"
    GEMINI_OVERVIEW_LOCATION: str = "global"
    GEMINI_OVERVIEW_MODEL_FALLBACKS: str = ""
    SERVICE_ACCOUNT_KEY_PATH: str = "service-account-key.json"
    BQ_DATASET: str = "kg_raw"
    OVERVIEW_RAG_DATASET: str = "multihopwanderer"
    OVERVIEW_RAG_EMBED_TABLE: str = "evidence_embeddings_pilot"
    OVERVIEW_RAG_ENTITY_TABLE: str = "evidence_doc_entities_pilot"
    OVERVIEW_EMBEDDING_MODEL: str = "gemini-embedding-001"
    OVERVIEW_EMBEDDING_MODEL_FALLBACK: str = "text-embedding-005"
    VERTEX_VECTOR_ENDPOINT_RESOURCE: str = ""
    VERTEX_VECTOR_DEPLOYED_INDEX_ID: str = ""
    GEMINI_DEEP_THINK_MODEL: str = "gemini-2.5-pro"
    SEMANTIC_SCHOLAR_API_KEY: str = ""
    OVERVIEW_HISTORY_LIMIT: int = 3
    OVERVIEW_RAG_TOP_K: int = 20
    OVERVIEW_RAG_FETCH_K: int = 150
    MAX_RELATED_ENTITIES: int = 50
    MAX_EVIDENCE_PER_EDGE: int = 5
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "https://benchspark-frontend-113940992739.us-central1.run.app",
        "https://benchspark-frontend-s7fuxsjnxq-uc.a.run.app",
    ]
    CORS_ORIGIN_REGEX: str = r"^https://benchspark-frontend(-[a-z0-9-]+)?\.us-central1\.run\.app$"

    # Cloud Spanner Graph (shortest-path traversal)
    SPANNER_INSTANCE_ID: str = "benchspark-graph"
    SPANNER_DATABASE_ID: str = "biograph"

    # ORKG (Open Research Knowledge Graph) evidence enrichment
    ORKG_BQ_TABLE: str = "orkg_contributions"
    ORKG_MAX_RESULTS: int = 10
    ORKG_ENABLED: bool = True


settings = Settings()
