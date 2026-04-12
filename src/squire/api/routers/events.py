"""Event timeline endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_db
from ..schemas import EventInfo, WatchTimelineItem

router = APIRouter()


@router.get("", response_model=list[EventInfo])
async def list_events(
    since: str | None = Query(None, description="ISO 8601 start timestamp"),
    category: str | None = Query(None, description="Filter by category"),
    session_id: str | None = Query(None, description="Filter by chat session ID"),
    watch_id: str | None = Query(None, description="Filter by watch ID"),
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
):
    """Query events with optional filters."""
    if since is None:
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    rows = await db.get_events(
        since,
        category=category,
        session_id=session_id,
        watch_id=watch_id,
        limit=limit,
    )
    return [EventInfo(**r) for r in rows]


@router.get("/timeline", response_model=list[WatchTimelineItem])
async def watch_timeline_events(
    watch_id: str | None = Query(None, description="Filter by watch ID"),
    watch_session_id: str | None = Query(None, description="Filter by watch session ID"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=200),
    db=Depends(get_db),
):
    """Unified timeline cards for investigation workbench."""
    rows = await db.get_watch_activity_timeline(
        watch_id=watch_id,
        watch_session_id=watch_session_id,
        page=page,
        per_page=per_page,
    )
    return [WatchTimelineItem(**r) for r in rows]
