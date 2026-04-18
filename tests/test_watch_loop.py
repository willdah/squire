"""Tests for watch loop helpers: command polling and interruptible sleep."""

import asyncio
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
async def test_poll_commands_reload_config_rebuilds_from_db(db, monkeypatch):
    """A 'reload_config' command should rebuild WatchConfig from DB overrides."""
    from squire.config import AppConfig, GuardrailsConfig, NotificationsConfig, WatchConfig
    from squire.notifications.router import NotificationRouter
    from squire.notifications.webhook import WebhookDispatcher
    from squire.watch import _poll_commands

    # DatabaseOverrideSource resolves the DB path via SQUIRE_DB_PATH env first.
    monkeypatch.setenv("SQUIRE_DB_PATH", str(db._db_path))

    shutdown = asyncio.Event()
    # Ensure schema is initialized before WatchConfig() reads it sync.
    await db.get_pending_watch_commands()

    config = WatchConfig()  # defaults — no overrides yet
    assert config.interval_minutes == 5

    # Write overrides AFTER config is built so the reload is the only thing that applies them.
    await db.set_config_section_overrides(
        "watch",
        {"interval_minutes": 1, "cycle_timeout_seconds": 120, "notify_on_action": False},
    )

    session_state = {"risk_tolerance": 2}

    class _FakeSession:
        def __init__(self) -> None:
            self.state: dict = {"risk_tolerance": 2}

    session_ref = [_FakeSession()]

    notifier = NotificationRouter(webhook=WebhookDispatcher(NotificationsConfig()), email=None, db=db)

    class _DummyAgent:
        before_tool_callback = None
        sub_agents: list = []

    agent = _DummyAgent()
    refs = {
        "app_config": AppConfig(),
        "agent": agent,
        "guardrails": GuardrailsConfig(),
        "notifier": notifier,
        "notifications": NotificationsConfig(),
    }

    await db.insert_watch_command("reload_config")
    await _poll_commands(
        db,
        shutdown,
        watch_config=config,
        session_ref=session_ref,
        session_state_template=session_state,
        refs=refs,
    )

    assert config.interval_minutes == 1
    assert config.cycle_timeout_seconds == 120
    assert config.notify_on_action is False
    assert not shutdown.is_set()

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0

    # The new notifier must have replaced the old one, and risk gates rewired.
    assert refs["notifier"] is not notifier
    assert agent.before_tool_callback is not None


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
    await _interruptible_sleep(db, shutdown, lambda: 60, poll_seconds=0.1, watch_config=None)
    assert shutdown.is_set()


@pytest.mark.asyncio
async def test_interruptible_sleep_honors_live_interval_change(db):
    """Shortening the interval mid-sleep via the getter should wake the sleep early."""
    from squire.watch import _interruptible_sleep

    shutdown = asyncio.Event()
    interval_holder = [5.0]  # starts at 5 seconds

    async def shrink():
        await asyncio.sleep(0.15)
        interval_holder[0] = 0.2  # below current elapsed; loop should exit

    await db.get_pending_watch_commands()  # initialize schema
    asyncio.create_task(shrink())

    start = asyncio.get_event_loop().time()
    await _interruptible_sleep(db, shutdown, lambda: interval_holder[0], poll_seconds=0.1, watch_config=None)
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 1.0, f"sleep did not honor shortened interval, took {elapsed:.2f}s"


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


@pytest.mark.asyncio
async def test_session_event_count_prefers_session_service_fetch():
    from squire.watch import _session_event_count

    class _SessionService:
        async def get_session(self, **kwargs):
            return SimpleNamespace(events=[1, 2, 3, 4])

    runner = SimpleNamespace(session_service=_SessionService())
    session = SimpleNamespace(id="sid", user_id="uid", events=[1])
    assert await _session_event_count(runner, session=session, app_name="Squire") == 4


@pytest.mark.asyncio
async def test_session_event_count_falls_back_to_local_session_on_error():
    from squire.watch import _session_event_count

    class _SessionService:
        async def get_session(self, **kwargs):
            raise RuntimeError("boom")

    runner = SimpleNamespace(session_service=_SessionService())
    session = SimpleNamespace(id="sid", user_id="uid", events=[1, 2])
    assert await _session_event_count(runner, session=session, app_name="Squire") == 2
