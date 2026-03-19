"""Tests for DatabaseService."""

import pytest


@pytest.mark.asyncio
async def test_snapshot_roundtrip(db):
    await db.save_snapshot({"hostname": "test", "cpu_percent": 42.0, "memory_used_mb": 1024, "memory_total_mb": 4096})
    snaps = await db.get_snapshots(since="2020-01-01")
    assert len(snaps) == 1
    assert snaps[0]["hostname"] == "test"
    assert snaps[0]["cpu_percent"] == 42.0


@pytest.mark.asyncio
async def test_session_lifecycle(db):
    await db.create_session("sess-1", preview="hello")
    sessions = await db.list_sessions()
    assert any(s["session_id"] == "sess-1" for s in sessions)

    await db.update_session_active("sess-1")
    sessions = await db.list_sessions()
    assert sessions[0]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_message_persistence(db):
    await db.create_session("sess-2")
    await db.save_message(session_id="sess-2", role="user", content="hello")
    await db.save_message(session_id="sess-2", role="assistant", content="hi there")

    msgs = await db.get_messages("sess-2")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "hi there"


@pytest.mark.asyncio
async def test_event_logging(db):
    await db.log_event(category="tool_call", summary="Called docker_ps", tool_name="docker_ps")
    events = await db.get_events(since="2020-01-01")
    assert len(events) == 1
    assert events[0]["category"] == "tool_call"
    assert events[0]["tool_name"] == "docker_ps"


@pytest.mark.asyncio
async def test_event_category_filter(db):
    await db.log_event(category="tool_call", summary="tool event")
    await db.log_event(category="error", summary="error event")

    tool_events = await db.get_events(since="2020-01-01", category="tool_call")
    assert len(tool_events) == 1
    assert tool_events[0]["category"] == "tool_call"


@pytest.mark.asyncio
async def test_empty_queries(db):
    assert await db.get_snapshots(since="2020-01-01") == []
    assert await db.get_messages("nonexistent") == []
    assert await db.list_sessions() == []


@pytest.mark.asyncio
async def test_delete_session(db):
    await db.create_session("sess-del", preview="to be deleted")
    await db.save_message(session_id="sess-del", role="user", content="hello")

    deleted = await db.delete_session("sess-del")
    assert deleted is True

    sessions = await db.list_sessions()
    assert not any(s["session_id"] == "sess-del" for s in sessions)
    assert await db.get_messages("sess-del") == []


@pytest.mark.asyncio
async def test_delete_session_not_found(db):
    deleted = await db.delete_session("nonexistent-session")
    assert deleted is False


@pytest.mark.asyncio
async def test_delete_all_sessions(db):
    await db.create_session("sess-a", preview="first")
    await db.create_session("sess-b", preview="second")
    await db.save_message(session_id="sess-a", role="user", content="hello")
    await db.save_message(session_id="sess-b", role="user", content="world")

    count = await db.delete_all_sessions()
    assert count == 2

    assert await db.list_sessions() == []
    assert await db.get_messages("sess-a") == []
    assert await db.get_messages("sess-b") == []


@pytest.mark.asyncio
async def test_delete_all_sessions_empty(db):
    count = await db.delete_all_sessions()
    assert count == 0
