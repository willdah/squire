"""System status and snapshot endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_db
from ..schemas import HostSnapshot, SnapshotRecord, SystemStatusResponse

router = APIRouter()


@router.get("/status", response_model=SystemStatusResponse)
async def system_status():
    """Current snapshot for all hosts."""
    from ..app import get_latest_snapshot

    snapshot = await get_latest_snapshot()
    hosts = {}
    for name, data in snapshot.items():
        hosts[name] = HostSnapshot(**data)
    return SystemStatusResponse(hosts=hosts)


@router.get("/snapshots", response_model=list[SnapshotRecord])
async def system_snapshots(
    since: str | None = Query(None, description="ISO 8601 start timestamp"),
    until: str | None = Query(None, description="ISO 8601 end timestamp"),
    host: str | None = Query(None, description="Filter by hostname"),
    db=Depends(get_db),
):
    """Historical snapshots for trend charts."""
    if since is None:
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    rows = await db.get_snapshots(since, until)
    if host:
        rows = [r for r in rows if r.get("hostname") == host]
    return [SnapshotRecord(**r) for r in rows]
