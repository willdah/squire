# tests/test_watch_emitter.py
"""Tests for WatchEventEmitter."""

import json
from unittest.mock import AsyncMock

import pytest

from squire.watch_emitter import WatchEventEmitter


@pytest.mark.asyncio
async def test_emit_cycle_start(db):
    emitter = WatchEventEmitter(db)
    await emitter.emit_cycle_start(cycle=1, session_id="s1")

    events = await db.get_watch_events_since(0)
    assert len(events) == 1
    assert events[0]["type"] == "cycle_start"
    content = json.loads(events[0]["content"])
    assert content["session_id"] == "s1"


@pytest.mark.asyncio
async def test_emit_tool_call(db):
    emitter = WatchEventEmitter(db)
    await emitter.emit_tool_call(cycle=1, tool_name="get_system_info", args={"host": "local"})

    events = await db.get_watch_events_since(0)
    assert len(events) == 1
    content = json.loads(events[0]["content"])
    assert content["name"] == "get_system_info"
    assert content["args"]["host"] == "local"


@pytest.mark.asyncio
async def test_emit_cycle_end_includes_stats(db):
    emitter = WatchEventEmitter(db)
    await emitter.emit_cycle_end(
        cycle=1,
        status="ok",
        duration_seconds=5.2,
        tool_count=3,
        blocked_count=1,
        outcome={"incident_count": 2},
    )

    events = await db.get_watch_events_since(0)
    content = json.loads(events[0]["content"])
    assert content["status"] == "ok"
    assert content["duration_seconds"] == 5.2
    assert content["tool_count"] == 3
    assert content["blocked_count"] == 1
    assert content["outcome"]["incident_count"] == 2


@pytest.mark.asyncio
async def test_emit_swallows_db_error():
    """Emission failures should be logged but never raised."""
    mock_db = AsyncMock()
    mock_db.insert_watch_event = AsyncMock(side_effect=RuntimeError("db down"))
    emitter = WatchEventEmitter(mock_db)
    # Should not raise
    await emitter.emit_token(cycle=1, content="hello")


@pytest.mark.asyncio
async def test_emit_approval_request(db):
    emitter = WatchEventEmitter(db)
    await emitter.emit_approval_request(
        cycle=1,
        request_id="req-1",
        tool_name="restart_container",
        args={"container": "nginx"},
        risk_level=4,
    )

    events = await db.get_watch_events_since(0)
    assert events[0]["type"] == "approval_request"
    content = json.loads(events[0]["content"])
    assert content["request_id"] == "req-1"
    assert content["risk_level"] == 4


@pytest.mark.asyncio
async def test_emit_phase_and_incident(db):
    emitter = WatchEventEmitter(db)
    await emitter.emit_phase(1, "detect", "Detected incident", details="details")
    await emitter.emit_incident(1, "key1", "high", "Disk pressure", "95%", "local")

    events = await db.get_watch_events_since(0)
    assert events[0]["type"] == "phase"
    assert events[1]["type"] == "incident"
