import uuid

# In-memory snapshot store — easily swappable to Firestore/GCS later
_store: dict[str, dict] = {}


def save_snapshot(data: dict) -> str:
    snapshot_id = uuid.uuid4().hex[:10]
    _store[snapshot_id] = data
    return snapshot_id


def load_snapshot(snapshot_id: str) -> dict | None:
    return _store.get(snapshot_id)
