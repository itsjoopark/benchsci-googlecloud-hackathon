from fastapi import APIRouter, HTTPException

from backend.models.snapshot import GraphSnapshotPayload, SnapshotResponse
from backend.services.snapshot_store import save_snapshot, load_snapshot

router = APIRouter(prefix="/api/graph", tags=["snapshot"])


@router.post("/snapshot", response_model=SnapshotResponse)
async def create_snapshot(payload: GraphSnapshotPayload):
    snapshot_id = save_snapshot(payload.model_dump())
    return SnapshotResponse(id=snapshot_id)


@router.get("/snapshot/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    data = load_snapshot(snapshot_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return data
