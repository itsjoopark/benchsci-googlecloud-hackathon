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
    SERVICE_ACCOUNT_KEY_PATH: str = "service-account-key.json"
    BQ_DATASET: str = "kg_raw"
    MAX_RELATED_ENTITIES: int = 50
    MAX_EVIDENCE_PER_EDGE: int = 5
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
    ]


settings = Settings()
