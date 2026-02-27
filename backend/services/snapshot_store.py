import uuid
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account

from backend.config import settings

_client: firestore.Client | None = None


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        kwargs: dict = {"project": settings.GCP_PROJECT_ID}
        sa_path = Path(settings.SERVICE_ACCOUNT_KEY_PATH)
        if sa_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(sa_path)
            )
            kwargs["credentials"] = credentials
        _client = firestore.Client(**kwargs)
    return _client


def save_snapshot(data: dict) -> str:
    snapshot_id = uuid.uuid4().hex[:10]
    _get_client().collection(settings.FIRESTORE_COLLECTION).document(snapshot_id).set(
        data
    )
    return snapshot_id


def load_snapshot(snapshot_id: str) -> dict | None:
    doc = (
        _get_client()
        .collection(settings.FIRESTORE_COLLECTION)
        .document(snapshot_id)
        .get()
    )
    return doc.to_dict() if doc.exists else None
