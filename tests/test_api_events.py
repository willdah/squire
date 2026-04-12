"""Tests for events API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_events_filters_by_session_and_watch(db):
    from squire.api.routers.events import list_events

    await db.log_event(category="tool_call", summary="session-a", session_id="sess-a")
    await db.log_event(category="tool_call", summary="session-b", session_id="sess-b")
    await db.log_event(category="watch.start", summary="watch-a", watch_id="watch-a")

    session_rows = await list_events(
        since="2020-01-01",
        category=None,
        session_id="sess-a",
        watch_id=None,
        limit=100,
        db=db,
    )
    assert len(session_rows) == 1
    assert session_rows[0].session_id == "sess-a"

    watch_rows = await list_events(
        since="2020-01-01",
        category=None,
        session_id=None,
        watch_id="watch-a",
        limit=100,
        db=db,
    )
    assert len(watch_rows) == 1
    assert watch_rows[0].watch_id == "watch-a"
