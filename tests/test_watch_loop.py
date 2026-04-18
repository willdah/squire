"""Tests for the pure helper functions in squire.watch_loop.

These were extracted out of ``squire.watch`` when the subprocess model was
replaced by an in-process ``WatchController``. Loop-lifecycle behavior
(start/stop/reload, crash → failed, holder lock) is covered in
``tests/test_watch_controller.py``.
"""

import asyncio
from types import SimpleNamespace

import pytest

from squire.watch_loop import (
    build_cycle_carryforward,
    build_session_outcome,
    build_session_report,
    build_watch_report,
    close_cancelled_cycle,
    session_event_count,
)


def test_build_cycle_carryforward_trims_long_fields():
    outcome = {
        "cycle_status": "ok",
        "incident_fingerprint": "disk-pressure",
        "actions": "a" * 600,
        "verification": "v" * 600,
        "escalation": "e" * 400,
    }
    carry = build_cycle_carryforward(outcome)
    assert carry["status"] == "ok"
    assert carry["incident_key"] == "disk-pressure"
    assert len(carry["actions"]) == 400
    assert len(carry["verification"]) == 400
    assert len(carry["watchouts"]) == 300


def test_build_session_outcome_empty():
    outcome = build_session_outcome([])
    assert outcome["status"] == "empty"
    assert "No cycles" in outcome["goal_summary"]


def test_build_session_outcome_mixed_statuses():
    cycles = [
        {"status": "ok", "resolved": True, "escalated": False},
        {"status": "error", "resolved": False, "escalated": True},
    ]
    outcome = build_session_outcome(cycles)
    assert outcome["status"] == "error"
    assert "1 resolved" in outcome["goal_summary"]
    assert "1 escalated" in outcome["goal_summary"]
    assert outcome["persistent_risks"]  # populated when any cycle escalated


def test_build_session_report_aggregates_counts():
    cycles = [
        {"tool_count": 2, "blocked_count": 0, "total_tokens": 10, "incident_count": 1},
        {"tool_count": 1, "blocked_count": 1, "total_tokens": 5, "incident_count": 0},
    ]
    outcome = {"status": "ok", "goal_summary": "summary", "persistent_risks": "", "open_actions": ""}
    report = build_session_report(watch_id="w1", watch_session_id="wss1", cycles=cycles, outcome=outcome)
    assert report["actions_taken"] == "3 remediation action(s) executed."
    assert report["blocked_or_denied_actions"] == "1 blocked/denied action(s)."
    assert report["cost_usage"] == {"total_tokens": 15, "cycle_count": 2}
    assert report["meta"]["watch_id"] == "w1"


def test_build_watch_report_infers_session_count_from_cycles():
    """Watch report should infer session count from cycle scope when session list is empty."""
    report = build_watch_report(
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


@pytest.mark.asyncio
async def test_close_cancelled_cycle_marks_cycle_cancelled(db):
    """Cancelling before cycle execution should close the cycle row."""
    from datetime import UTC, datetime

    await db.create_watch_run("watch_cancel")
    await db.create_watch_session("wss_cancel", watch_id="watch_cancel", adk_session_id="adk_cancel")
    await db.create_watch_cycle(
        "cyc_cancel",
        watch_id="watch_cancel",
        watch_session_id="wss_cancel",
        cycle_number=1,
    )

    cycle_row = await close_cancelled_cycle(
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


@pytest.mark.asyncio
async def test_session_event_count_prefers_session_service_fetch():
    class _SessionService:
        async def get_session(self, **kwargs):
            return SimpleNamespace(events=[1, 2, 3, 4])

    runner = SimpleNamespace(session_service=_SessionService())
    session = SimpleNamespace(id="sid", user_id="uid", events=[1])
    assert await session_event_count(runner, session=session, app_name="Squire") == 4


@pytest.mark.asyncio
async def test_session_event_count_falls_back_to_local_session_on_error():
    class _SessionService:
        async def get_session(self, **kwargs):
            raise RuntimeError("boom")

    runner = SimpleNamespace(session_service=_SessionService())
    session = SimpleNamespace(id="sid", user_id="uid", events=[1, 2])
    assert await session_event_count(runner, session=session, app_name="Squire") == 2


@pytest.mark.asyncio
async def test_interruptible_sleep_is_replaced_by_controller(db):
    """Sanity check that the old DB-polled sleep no longer exists as a public symbol."""
    import squire.watch_loop as loop

    assert not hasattr(loop, "_interruptible_sleep")
    assert not hasattr(loop, "_poll_commands")


@pytest.mark.asyncio
async def test_event_loop_is_available(db):
    """Trivial async-safety check to ensure fixtures wire up correctly."""
    assert asyncio.get_running_loop() is not None
