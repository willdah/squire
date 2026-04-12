"""Tests for watch loop helpers: command polling and interruptible sleep."""

import asyncio
import json
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_poll_commands_stop(db):
    """A 'stop' command should set the shutdown event."""
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    await db.insert_watch_command("stop")

    await _poll_commands(db, shutdown, watch_config=None)
    assert shutdown.is_set()

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_poll_commands_update_config(db):
    """An 'update_config' command should apply overrides."""
    from squire.config import WatchConfig
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    config = WatchConfig()
    session_state = {"risk_tolerance": 2}

    class _FakeSession:
        def __init__(self) -> None:
            self.state: dict = {"risk_tolerance": 2}

    session_ref = [_FakeSession()]

    await db.insert_watch_command(
        "update_config",
        payload=json.dumps(
            {
                "interval_minutes": 1,
                "cycle_timeout_seconds": 120,
                "notify_on_action": False,
                "risk_tolerance": 5,
            }
        ),
    )
    await _poll_commands(
        db,
        shutdown,
        watch_config=config,
        session_ref=session_ref,
        session_state_template=session_state,
    )

    assert config.interval_minutes == 1
    assert config.cycle_timeout_seconds == 120
    assert config.notify_on_action is False
    assert session_ref[0].state["risk_tolerance"] == 5
    assert session_state["risk_tolerance"] == 5
    assert not shutdown.is_set()

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_poll_commands_update_config_rejects_invalid_safety_values(db):
    """Invalid live safety updates should fail and keep existing values."""
    from squire.config import WatchConfig
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    config = WatchConfig()
    initial_identical_limit = config.max_identical_actions_per_cycle

    cmd_id = await db.insert_watch_command(
        "update_config",
        payload=json.dumps({"max_identical_actions_per_cycle": 0}),
    )
    await _poll_commands(db, shutdown, watch_config=config)

    assert config.max_identical_actions_per_cycle == initial_identical_limit
    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0

    conn = await db._get_conn()  # noqa: SLF001 - test verifies command status persistence
    cursor = await conn.execute("SELECT status, error FROM watch_commands WHERE id = ?", (cmd_id,))
    row = await cursor.fetchone()
    assert row["status"] == "failed"
    assert "max_identical_actions_per_cycle" in (row["error"] or "")


@pytest.mark.asyncio
async def test_poll_commands_unknown_fails(db):
    """Unknown commands should be marked as failed."""
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    await db.insert_watch_command("unknown_cmd")

    await _poll_commands(db, shutdown, watch_config=None)

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_interruptible_sleep_responds_to_commands(db):
    """Sleep should break out when a stop command is inserted."""
    from squire.watch import _interruptible_sleep

    shutdown = asyncio.Event()

    # Ensure schema is created before spawning the background task.
    # Without this, the background insert and the poll can race to
    # initialize the DB connection concurrently on Python 3.13+.
    await db.get_pending_watch_commands()

    async def insert_stop():
        await asyncio.sleep(0.2)
        await db.insert_watch_command("stop")

    asyncio.create_task(insert_stop())
    await _interruptible_sleep(db, shutdown, interval_seconds=60, poll_seconds=0.1, watch_config=None)
    assert shutdown.is_set()


@pytest.mark.asyncio
async def test_close_cancelled_cycle_marks_cycle_cancelled(db):
    """Cancelling before cycle execution should close the cycle row."""
    from datetime import UTC, datetime

    from squire.watch import _close_cancelled_cycle

    await db.create_watch_run("watch_cancel")
    await db.create_watch_session("wss_cancel", watch_id="watch_cancel", adk_session_id="adk_cancel")
    await db.create_watch_cycle(
        "cyc_cancel",
        watch_id="watch_cancel",
        watch_session_id="wss_cancel",
        cycle_number=1,
    )

    cycle_row = await _close_cancelled_cycle(
        db,
        cycle_id="cyc_cancel",
        watch_session_id="wss_cancel",
        cycle_started_at=datetime.now(UTC),
    )
    assert cycle_row["status"] == "cancelled"
    assert cycle_row["cycle_id"] == "cyc_cancel"
    assert cycle_row["watch_session_id"] == "wss_cancel"

    cycles = await db.list_watch_cycles_for_session("watch_cancel", "wss_cancel", page=1, per_page=20)
    assert len(cycles) == 1
    assert cycles[0]["status"] == "cancelled"


def test_build_watch_report_infers_session_count_from_cycles():
    """Watch report should infer session count from cycle scope when session list is empty."""
    from squire.watch import _build_watch_report

    report = _build_watch_report(
        watch_id="watch_report_scope",
        sessions=[],
        cycles=[
            {"watch_session_id": "wss_a", "tool_count": 2, "status": "ok", "incident_count": 1, "total_tokens": 10},
            {"watch_session_id": "wss_a", "tool_count": 1, "status": "ok", "incident_count": 0, "total_tokens": 5},
            {"watch_session_id": "wss_b", "tool_count": 0, "status": "error", "incident_count": 1, "total_tokens": 7},
        ],
    )
    assert "2 session(s) and 3 cycle(s)" in report["run_summary"]
    assert report["major_actions"] == "3 actions executed."


def test_session_event_count_uses_public_events_attribute():
    from squire.watch import _session_event_count

    assert _session_event_count(SimpleNamespace(events=[1, 2, 3])) == 3
    assert _session_event_count(SimpleNamespace(events=None)) == 0
    assert _session_event_count(SimpleNamespace()) == 0
