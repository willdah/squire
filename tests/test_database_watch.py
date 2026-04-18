"""Tests for watch_events, watch_commands, and watch_approvals tables."""

import json

import pytest


@pytest.mark.asyncio
async def test_insert_and_tail_watch_events(db):
    """Insert events and tail by ID."""
    id1 = await db.insert_watch_event(cycle=1, type="cycle_start", content=json.dumps({"session_id": "s1"}))
    id2 = await db.insert_watch_event(cycle=1, type="token", content="hello")
    id3 = await db.insert_watch_event(cycle=1, type="cycle_end", content=json.dumps({"status": "ok"}))

    # Tail from the beginning
    events = await db.get_watch_events_since(0)
    assert len(events) == 3
    assert events[0]["id"] == id1
    assert events[2]["id"] == id3

    # Tail from after first event
    events = await db.get_watch_events_since(id1)
    assert len(events) == 2
    assert events[0]["id"] == id2


@pytest.mark.asyncio
async def test_get_events_for_cycle(db):
    """Filter events by cycle number."""
    await db.insert_watch_event(cycle=1, type="token", content="a")
    await db.insert_watch_event(cycle=2, type="token", content="b")
    await db.insert_watch_event(cycle=1, type="token", content="c")

    events = await db.get_watch_events_for_cycle(1)
    assert len(events) == 2
    assert all(e["cycle"] == 1 for e in events)


@pytest.mark.asyncio
async def test_get_watch_cycles(db):
    """Aggregate cycles from start/end events."""
    await db.insert_watch_event(cycle=1, type="cycle_start", content=json.dumps({"session_id": "s1"}))
    await db.insert_watch_event(cycle=1, type="tool_call", content=json.dumps({"name": "get_system_info"}))
    end1 = json.dumps({"status": "ok", "duration_seconds": 5.2, "tool_count": 1})
    await db.insert_watch_event(cycle=1, type="cycle_end", content=end1)
    await db.insert_watch_event(cycle=2, type="cycle_start", content=json.dumps({"session_id": "s1"}))
    end2 = json.dumps({"status": "error", "duration_seconds": 2.0, "tool_count": 0})
    await db.insert_watch_event(cycle=2, type="cycle_end", content=end2)

    cycles = await db.get_watch_cycles(page=1, per_page=10)
    assert len(cycles) == 2
    assert cycles[0]["cycle"] == 2  # Most recent first
    assert cycles[1]["cycle"] == 1


@pytest.mark.asyncio
async def test_watch_commands_table_is_dropped_by_migration(db):
    """The legacy watch_commands table is removed by the forward-only migration."""
    conn = await db._get_conn()
    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='watch_commands'")
    row = await cursor.fetchone()
    assert row is None


@pytest.mark.asyncio
async def test_claim_watch_holder_rejects_second_holder(db):
    """A second holder cannot claim the lock while the first holder's TTL is valid."""
    assert await db.claim_watch_holder("holder-a", ttl_seconds=60) is True
    assert await db.claim_watch_holder("holder-b", ttl_seconds=60) is False
    # Idempotent reclaim by the same holder is allowed.
    assert await db.claim_watch_holder("holder-a", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_claim_watch_holder_allows_reclaim_after_expiry(db):
    """An expired holder row lets a new holder claim the lock."""
    assert await db.claim_watch_holder("holder-a", ttl_seconds=-1) is True
    # The row exists but is already expired, so holder-b can take over.
    assert await db.claim_watch_holder("holder-b", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_heartbeat_refreshes_and_detects_takeover(db):
    """heartbeat_watch_holder refreshes the TTL; a different holder makes it return False."""
    await db.claim_watch_holder("holder-a", ttl_seconds=60)
    assert await db.heartbeat_watch_holder("holder-a", ttl_seconds=60) is True

    # Simulate holder-a releasing and holder-b taking the lock.
    await db.release_watch_holder("holder-a")
    await db.claim_watch_holder("holder-b", ttl_seconds=60)
    # holder-a's heartbeat should now report that it no longer owns the lock.
    assert await db.heartbeat_watch_holder("holder-a", ttl_seconds=60) is False

    # Heartbeat when no row exists returns False too.
    await db.release_watch_holder("holder-b")
    assert await db.heartbeat_watch_holder("holder-a", ttl_seconds=60) is False


@pytest.mark.asyncio
async def test_release_watch_holder_is_scoped_by_holder_id(db):
    """release_watch_holder only deletes if the caller currently holds the lock."""
    await db.claim_watch_holder("holder-a", ttl_seconds=60)
    await db.release_watch_holder("holder-b")  # no-op
    # holder-a still owns it.
    assert await db.claim_watch_holder("holder-b", ttl_seconds=60) is False

    await db.release_watch_holder("holder-a")
    assert await db.claim_watch_holder("holder-b", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_finalize_stale_watch_runs_on_boot_closes_all_running(db):
    """Every ``running`` watch run gets finalized in a single boot pass."""
    await db.create_watch_run("watch_boot_a")
    await db.create_watch_session("wss_boot_a", watch_id="watch_boot_a", adk_session_id="adk_boot_a")
    await db.create_watch_run("watch_boot_b")
    await db.create_watch_session("wss_boot_b", watch_id="watch_boot_b", adk_session_id="adk_boot_b")

    finalized = await db.finalize_stale_watch_runs_on_boot()
    assert set(finalized) == {"watch_boot_a", "watch_boot_b"}

    for watch_id in ("watch_boot_a", "watch_boot_b"):
        run = await db.get_watch_run(watch_id)
        assert run is not None
        assert run["status"] == "stopped"

    # The holder row (if any) is cleared on boot so the next controller can claim it.
    await db.claim_watch_holder("new-holder", ttl_seconds=60)
    await db.finalize_stale_watch_runs_on_boot()
    # After boot cleanup, a brand new holder can take the lock without contention.
    assert await db.claim_watch_holder("post-boot", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_approval_lifecycle(db):
    """Full approval flow: insert, get, update, verify."""
    await db.insert_watch_approval(
        request_id="req-1",
        tool_name="restart_container",
        args=json.dumps({"container": "nginx"}),
        risk_level=4,
    )

    approval = await db.get_watch_approval("req-1")
    assert approval is not None
    assert approval["status"] == "pending"
    assert approval["tool_name"] == "restart_container"

    await db.update_watch_approval("req-1", "approved")
    approval = await db.get_watch_approval("req-1")
    assert approval["status"] == "approved"
    assert approval["responded_at"] is not None


@pytest.mark.asyncio
async def test_approval_not_found(db):
    """Non-existent approval returns None."""
    result = await db.get_watch_approval("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_watch_cycles(db):
    """delete_watch_cycles removes all watch events but preserves approvals."""
    await db.insert_watch_event(cycle=1, type="cycle_start", content="{}")
    await db.insert_watch_event(cycle=1, type="cycle_end", content="{}")
    await db.insert_watch_event(cycle=2, type="cycle_start", content="{}")
    await db.insert_watch_event(cycle=2, type="cycle_end", content="{}")
    await db.insert_watch_approval(request_id="req-1", tool_name="test", args="{}", risk_level=3)

    await db.delete_watch_cycles()

    events = await db.get_watch_events_since(0)
    assert events == []
    cycles = await db.get_watch_cycles()
    assert cycles == []
    # Approvals must be preserved
    approval = await db.get_watch_approval("req-1")
    assert approval is not None


@pytest.mark.asyncio
async def test_cleanup_watch_data(db):
    """Cleanup removes old events but keeps recent ones."""
    await db.create_watch_run("watch_cleanup")
    await db.create_watch_session("wss_cleanup", watch_id="watch_cleanup", adk_session_id="adk_cleanup")
    await db.create_watch_cycle(
        "cyc_cleanup_1",
        watch_id="watch_cleanup",
        watch_session_id="wss_cleanup",
        cycle_number=1,
    )
    await db.close_watch_cycle(
        "cyc_cleanup_1",
        status="ok",
        duration_seconds=1.0,
        tool_count=0,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=0,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        incident_key=None,
        outcome={},
    )
    await db.insert_watch_event(cycle=1, cycle_id="cyc_cleanup_1", type="cycle_start", content="{}")
    await db.insert_watch_event(cycle=1, cycle_id="cyc_cleanup_1", type="cycle_end", content="{}")

    await db.create_watch_cycle(
        "cyc_cleanup_2",
        watch_id="watch_cleanup",
        watch_session_id="wss_cleanup",
        cycle_number=2,
    )
    await db.close_watch_cycle(
        "cyc_cleanup_2",
        status="ok",
        duration_seconds=1.0,
        tool_count=0,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=0,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        incident_key=None,
        outcome={},
    )
    await db.insert_watch_event(cycle=2, cycle_id="cyc_cleanup_2", type="cycle_start", content="{}")
    await db.insert_watch_event(cycle=2, cycle_id="cyc_cleanup_2", type="cycle_end", content="{}")

    deleted = await db.cleanup_watch_data(max_cycles=1)
    assert deleted > 0

    remaining = await db.get_watch_events_since(0, limit=100, watch_id="watch_cleanup")
    assert all(e["cycle_id"] == "cyc_cleanup_2" for e in remaining)


@pytest.mark.asyncio
async def test_finalize_stale_watch_run_creates_reports_and_closes_rows(db):
    """Stale watch finalization should persist watch/session reports and close records."""
    await db.create_watch_run("watch_stale_db")
    await db.create_watch_session("wss_stale_db", watch_id="watch_stale_db", adk_session_id="adk_stale_db")
    await db.create_watch_cycle(
        "cyc_stale_1",
        watch_id="watch_stale_db",
        watch_session_id="wss_stale_db",
        cycle_number=1,
    )
    await db.close_watch_cycle(
        "cyc_stale_1",
        status="ok",
        duration_seconds=1.2,
        tool_count=2,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        incident_key="disk",
        outcome={"resolved": True},
    )
    await db.create_watch_cycle(
        "cyc_stale_2",
        watch_id="watch_stale_db",
        watch_session_id="wss_stale_db",
        cycle_number=2,
    )
    await db.close_watch_cycle(
        "cyc_stale_2",
        status="error",
        duration_seconds=0.7,
        tool_count=1,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=6,
        output_tokens=3,
        total_tokens=9,
        incident_key="service",
        outcome={"resolved": False},
        error_reason="timeout",
    )

    result = await db.finalize_stale_watch_run("watch_stale_db", watch_session_id="wss_stale_db")
    assert result["watch_report_id"] is not None
    assert result["session_report_id"] is not None

    run = await db.get_watch_run("watch_stale_db")
    assert run is not None
    assert run["status"] == "stopped"

    sessions = await db.list_watch_sessions_for_run("watch_stale_db", page=1, per_page=20)
    assert len(sessions) == 1
    assert sessions[0]["status"] == "stopped"
    assert sessions[0]["session_report_id"] is not None

    watch_report = await db.get_watch_completion_report("watch_stale_db")
    assert watch_report is not None
    assert watch_report["report_type"] == "watch"
    payload = json.loads(watch_report["report_json"])
    assert "1 session(s) and 2 cycle(s)" in payload["run_summary"]
    assert payload["major_actions"] == "3 actions executed."
