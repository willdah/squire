"""Tests for the in-process WatchController.

These tests exercise the controller's control plane directly — lifecycle
(start/stop/reload/status), supervisor failure handling, the DB-backed
holder lock, and the auto-start-on-boot flag — without spinning up a real
agent/runner. The heavy inner loop (``_run_loop``) is replaced with a stub
so tests run in milliseconds.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from squire.config import (
    AppConfig,
    GuardrailsConfig,
    LLMConfig,
    NotificationsConfig,
    WatchConfig,
)
from squire.config.app import RiskTolerance
from squire.database.service import DatabaseService
from squire.watch_controller import WatchController, _effective_watch_risk_tolerance, _headless_risk_gate


@pytest_asyncio.fixture
async def db(tmp_path):
    db = DatabaseService(tmp_path / "test.db")
    yield db
    await db.close()


def _make_controller(db: DatabaseService) -> WatchController:
    """Build a controller with real configs and stand-in services.

    The inner loop (``_run_loop``) is monkey-patched per-test so we never
    actually spin up an ADK agent.
    """
    return WatchController(
        db=db,
        registry=object(),
        adk_runtime=object(),
        skill_service=object(),
        app_config=AppConfig(),
        llm_config=LLMConfig(),
        watch_config=WatchConfig(),
        guardrails=GuardrailsConfig(),
        notifications=NotificationsConfig(),
        notifier=object(),
    )


@pytest.mark.asyncio
async def test_start_transitions_through_running_then_stopped(db, monkeypatch):
    """A loop that returns cleanly flows stopped → running → stopped."""
    controller = _make_controller(db)

    started = asyncio.Event()

    async def _fake_loop(self):
        started.set()
        # yield once so the caller can observe the running state
        await asyncio.sleep(0)

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    assert controller.status().state == "stopped"
    result = await controller.start()
    assert result.status == "ok"
    await asyncio.wait_for(started.wait(), timeout=1.0)
    # Wait for the stub to complete; the supervisor then flips to stopped.
    await asyncio.wait_for(controller._task, timeout=1.0)
    assert controller.status().state == "stopped"


@pytest.mark.asyncio
async def test_start_is_idempotent_when_already_running(db, monkeypatch):
    """Calling start twice while the task is alive returns 'already_running'."""
    controller = _make_controller(db)
    never_ends = asyncio.Event()

    async def _fake_loop(self):
        await never_ends.wait()

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    try:
        first = await controller.start()
        assert first.status == "ok"
        # Give the supervisor a chance to flip to running before we inspect it.
        for _ in range(20):
            if controller.status().state == "running":
                break
            await asyncio.sleep(0.01)
        second = await controller.start()
        assert second.status == "ok"
        assert "already running" in second.message.lower()
    finally:
        never_ends.set()
        await controller.stop(timeout=1.0)


@pytest.mark.asyncio
async def test_stop_releases_holder_and_flips_to_stopped(db, monkeypatch):
    """stop() signals shutdown, awaits the task, and releases the DB holder lock."""
    controller = _make_controller(db)

    async def _fake_loop(self):
        await self._shutdown.wait()

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    await controller.start()
    # Holder row should exist while the controller is running.
    row = await db.get_watch_state("watch_holder")
    assert row is not None and controller._holder_id in row

    await controller.stop(timeout=1.0)
    assert controller.status().state == "stopped"
    # Lock released on clean stop.
    assert await db.get_watch_state("watch_holder") is None


@pytest.mark.asyncio
async def test_crash_flips_state_to_failed_and_captures_error(db, monkeypatch):
    """An uncaught exception in the loop surfaces as state='failed' with last_error."""
    controller = _make_controller(db)

    async def _fake_loop(self):
        raise RuntimeError("simulated cycle explosion")

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    await controller.start()
    await asyncio.wait_for(controller._task, timeout=1.0)

    runtime = controller.status()
    assert runtime.state == "failed"
    assert runtime.last_error is not None
    assert "simulated cycle explosion" in runtime.last_error


@pytest.mark.asyncio
async def test_holder_lock_blocks_second_controller(db, monkeypatch):
    """A second controller cannot start while the first holds the DB holder lock."""
    controller_a = _make_controller(db)
    controller_b = _make_controller(db)
    never_ends = asyncio.Event()

    async def _fake_loop(self):
        await never_ends.wait()

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    try:
        result_a = await controller_a.start()
        assert result_a.status == "ok"

        result_b = await controller_b.start()
        assert result_b.status == "holder_busy"
        assert controller_b.status().state == "stopped"
    finally:
        never_ends.set()
        await controller_a.stop(timeout=1.0)
        await controller_b.stop(timeout=1.0)


@pytest.mark.asyncio
async def test_reload_event_is_observed_by_the_loop(db, monkeypatch):
    """Calling reload() sets the asyncio.Event the loop polls."""
    controller = _make_controller(db)
    observed = asyncio.Event()

    async def _fake_loop(self):
        while not self._shutdown.is_set():
            if self._reload.is_set():
                observed.set()
                self._reload.clear()
            await asyncio.sleep(0.01)

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    try:
        await controller.start()
        controller.reload()
        await asyncio.wait_for(observed.wait(), timeout=1.0)
    finally:
        await controller.stop(timeout=1.0)


@pytest.mark.asyncio
async def test_stop_cancels_task_when_timeout_exceeded(db, monkeypatch):
    """If the loop refuses to exit gracefully, stop() cancels it after the timeout."""
    controller = _make_controller(db)
    loop_started = asyncio.Event()

    async def _fake_loop(self):
        loop_started.set()
        # Ignore _shutdown entirely to force the cancellation path.
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise

    monkeypatch.setattr(WatchController, "_run_loop", _fake_loop)

    await controller.start()
    await asyncio.wait_for(loop_started.wait(), timeout=1.0)

    # Tiny timeout forces the cancel path; stop() must return cleanly.
    await controller.stop(timeout=0.05)
    assert controller.status().state == "stopped"
    assert await db.get_watch_state("watch_holder") is None


@pytest.mark.asyncio
async def test_stop_releases_holder_even_if_task_never_started(db):
    """Calling stop() before start() is a no-op that still clears any stale holder row."""
    controller = _make_controller(db)
    # Seed a holder row as if a crash left it behind.
    await db.claim_watch_holder(controller._holder_id, ttl_seconds=60)
    await controller.stop(timeout=0.1)
    assert await db.get_watch_state("watch_holder") is None


def test_headless_risk_gate_wires_approval_provider(monkeypatch):
    captured = {}

    def _fake_create_risk_gate(
        *,
        tool_risk_levels,
        risk_overrides,
        default_threshold,
        headless,
        notifier,
        approval_provider,
        rate_limit_gate=None,
    ):
        captured["tool_risk_levels"] = tool_risk_levels
        captured["risk_overrides"] = risk_overrides
        captured["default_threshold"] = default_threshold
        captured["headless"] = headless
        captured["notifier"] = notifier
        captured["approval_provider"] = approval_provider
        captured["rate_limit_gate"] = rate_limit_gate
        return object()

    monkeypatch.setattr("squire.watch_controller.create_risk_gate", _fake_create_risk_gate)
    provider = object()
    result = _headless_risk_gate(
        {"run_command": 5},
        guardrails=GuardrailsConfig(),
        notifier=None,
        approval_provider=provider,
    )
    assert result is not None
    assert captured["headless"] is True
    assert captured["approval_provider"] is provider


class TestEffectiveWatchRiskTolerance:
    """Regression: autonomy-mode helper must normalize enum/str tolerances to ints."""

    def test_accepts_risk_tolerance_enum(self):
        # Regression: passing a RiskTolerance enum used to crash with
        # "TypeError: '>' not supported between instances of 'int' and 'RiskTolerance'".
        assert _effective_watch_risk_tolerance(RiskTolerance.STANDARD, "supervised") == 3
        assert _effective_watch_risk_tolerance(RiskTolerance.STANDARD, "autonomous") == 4

    def test_accepts_string_alias(self):
        assert _effective_watch_risk_tolerance("cautious", "supervised") == 2
        assert _effective_watch_risk_tolerance("cautious", "autonomous") == 4

    def test_accepts_int(self):
        assert _effective_watch_risk_tolerance(2, "supervised") == 2
        assert _effective_watch_risk_tolerance(2, "autonomous") == 4

    def test_autonomous_never_regresses_above_ceiling(self):
        # Already at full-trust (5): autonomous must not cap at 4.
        assert _effective_watch_risk_tolerance(RiskTolerance.FULL_TRUST, "autonomous") == 5
