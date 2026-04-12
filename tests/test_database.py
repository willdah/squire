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
    await db.save_message(
        session_id="sess-2",
        role="assistant",
        content="hi there",
        input_tokens=12,
        output_tokens=9,
        total_tokens=21,
    )

    msgs = await db.get_messages("sess-2")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "hi there"
    assert msgs[1]["input_tokens"] == 12
    assert msgs[1]["output_tokens"] == 9
    assert msgs[1]["total_tokens"] == 21


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
async def test_event_filters_by_session_and_watch(db):
    await db.log_event(category="tool_call", summary="chat-a", session_id="sess-a")
    await db.log_event(category="tool_call", summary="chat-b", session_id="sess-b")
    await db.log_event(category="watch.start", summary="watch-a", watch_id="watch-a")
    await db.log_event(
        category="watch.alert",
        summary="watch-a-cycle",
        watch_id="watch-a",
        watch_session_id="wss-a",
        cycle_id="cyc-a",
    )

    sess_a = await db.get_events(since="2020-01-01", session_id="sess-a")
    assert len(sess_a) == 1
    assert sess_a[0]["summary"] == "chat-a"

    watch_a = await db.get_events(since="2020-01-01", watch_id="watch-a")
    assert len(watch_a) == 2
    assert all(event["watch_id"] == "watch-a" for event in watch_a)
    assert any(event["cycle_id"] == "cyc-a" for event in watch_a)


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


@pytest.mark.asyncio
async def test_list_sessions_includes_token_totals(db):
    await db.create_session("sess-tokens")
    await db.save_message(
        session_id="sess-tokens",
        role="assistant",
        content="first",
        input_tokens=10,
        output_tokens=8,
        total_tokens=18,
    )
    await db.save_message(
        session_id="sess-tokens",
        role="assistant",
        content="second",
        input_tokens=5,
        output_tokens=7,
        total_tokens=12,
    )

    sessions = await db.list_sessions()
    session = next(s for s in sessions if s["session_id"] == "sess-tokens")
    assert session["input_tokens"] == 15
    assert session["output_tokens"] == 15
    assert session["total_tokens"] == 30


@pytest.mark.asyncio
async def test_watch_cycles_include_token_counts(db):
    await db.insert_watch_event(1, "cycle_start", '{"session_id":"sess-w"}')
    await db.insert_watch_event(
        1,
        "cycle_end",
        '{"status":"ok","duration_seconds":2.5,"tool_count":1,"input_tokens":42,"output_tokens":17,"total_tokens":59}',
    )

    cycles = await db.get_watch_cycles(page=1, per_page=10)
    assert len(cycles) == 1
    assert cycles[0]["input_tokens"] == 42
    assert cycles[0]["output_tokens"] == 17
    assert cycles[0]["total_tokens"] == 59


@pytest.mark.asyncio
async def test_watch_cycles_scoped_by_watch_and_session(db):
    await db.create_watch_run("watch_a")
    await db.create_watch_run("watch_b")
    await db.create_watch_session("wss_a1", watch_id="watch_a", adk_session_id="adk_a1")
    await db.create_watch_session("wss_b1", watch_id="watch_b", adk_session_id="adk_b1")
    await db.create_watch_cycle("cyc_a1", watch_id="watch_a", watch_session_id="wss_a1", cycle_number=1)
    await db.create_watch_cycle("cyc_b1", watch_id="watch_b", watch_session_id="wss_b1", cycle_number=1)
    await db.close_watch_cycle(
        "cyc_a1",
        status="ok",
        duration_seconds=1.0,
        tool_count=1,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=7,
        output_tokens=3,
        total_tokens=10,
        incident_key="inc-a",
        outcome={"resolved": True},
    )
    await db.close_watch_cycle(
        "cyc_b1",
        status="error",
        duration_seconds=2.0,
        tool_count=0,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        incident_key="inc-b",
        outcome={"resolved": False},
        error_reason="timeout",
    )

    watch_a_cycles = await db.get_watch_cycles(watch_id="watch_a")
    watch_b_cycles = await db.get_watch_cycles(watch_id="watch_b")
    assert len(watch_a_cycles) == 1
    assert len(watch_b_cycles) == 1
    assert watch_a_cycles[0]["cycle_id"] == "cyc_a1"
    assert watch_b_cycles[0]["cycle_id"] == "cyc_b1"


@pytest.mark.asyncio
async def test_watch_hierarchy_queries(db):
    await db.create_watch_run("watch_h1")
    await db.create_watch_session("wss_h1", watch_id="watch_h1", adk_session_id="adk_h1")
    await db.create_watch_cycle("cyc_h1", watch_id="watch_h1", watch_session_id="wss_h1", cycle_number=1)
    await db.close_watch_cycle(
        "cyc_h1",
        status="ok",
        duration_seconds=2.2,
        tool_count=1,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=4,
        output_tokens=3,
        total_tokens=7,
        incident_key="inc-h",
        outcome={"resolved": True},
    )
    await db.create_watch_report(
        "rep_wh1",
        watch_id="watch_h1",
        watch_session_id=None,
        report_type="watch",
        status="ok",
        title="Watch report",
        digest="Done",
        report={"run_summary": "done"},
    )
    await db.create_watch_report(
        "rep_sh1",
        watch_id="watch_h1",
        watch_session_id="wss_h1",
        report_type="session",
        status="ok",
        title="Session report",
        digest="Done",
        report={"executive_summary": "done"},
    )

    runs = await db.list_watch_runs(page=1, per_page=10)
    assert len(runs) == 1
    assert runs[0]["watch_id"] == "watch_h1"
    assert runs[0]["report_count"] == 2
    assert runs[0]["watch_report_id"] == "rep_wh1"

    run = await db.get_watch_run("watch_h1")
    assert run is not None
    assert run["session_count"] == 1

    sessions = await db.list_watch_sessions_for_run("watch_h1")
    assert len(sessions) == 1
    assert sessions[0]["session_report_id"] == "rep_sh1"
    assert sessions[0]["session_report_title"] == "Session report"

    cycles = await db.list_watch_cycles_for_session("watch_h1", "wss_h1")
    assert len(cycles) == 1
    assert cycles[0]["cycle_id"] == "cyc_h1"
