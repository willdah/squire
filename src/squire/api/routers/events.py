"""Event timeline endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_db
from ..schemas import EventInfo

router = APIRouter()


@router.get("", response_model=list[EventInfo])
async def list_events(
    since: str | None = Query(None, description="ISO 8601 start timestamp"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
):
    """Query events with optional filters."""
    if since is None:
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    rows = await db.get_events(since, category=category, limit=limit)
    return [EventInfo(**r) for r in rows]
