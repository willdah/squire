"""Tests for watch loop helpers: command polling and interruptible sleep."""

import asyncio
import json

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
    from agent_risk_engine import RiskEvaluator, RuleGate

    from squire.callbacks.risk_gate import build_pattern_analyzer
    from squire.config import WatchConfig
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    config = WatchConfig()
    rule_gate = RuleGate(threshold=2, strict=True, allowed=set(), denied=set())
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate, analyzer=build_pattern_analyzer())
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
        risk_evaluator=risk_evaluator,
    )

    assert config.interval_minutes == 1
    assert config.cycle_timeout_seconds == 120
    assert config.notify_on_action is False
    assert risk_evaluator.rule_gate.threshold == 5
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
