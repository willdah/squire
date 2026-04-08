"""Tests for wait_for_state tool."""

import asyncio
import json

import pytest

from squire.monitoring.sinks import register_monitor_session_sink, unregister_monitor_session_sink
from squire.system.backend import CommandResult
from squire.tools.wait_for_state import wait_for_state


class _FakeSession:
    id = "sess-test"


class _FakeToolContext:
    session = _FakeSession()


@pytest.mark.asyncio
async def test_wait_running_blocking(mock_registry, mock_backend):
    """Without a session sink, polling runs inline until success."""
    state = {"Running": True, "Status": "running", "ExitCode": 0}
    mock_backend.set_response("docker", CommandResult(returncode=0, stdout=json.dumps(state), stderr=""))

    out = await wait_for_state(
        "docker_container",
        "nginx",
        "running",
        host="local",
        interval_seconds=1,
        timeout_seconds=5,
        tool_context=_FakeToolContext(),
    )
    assert "nginx" in out
    assert "running" in out.lower() or "✓" in out


@pytest.mark.asyncio
async def test_healthy_fails_without_healthcheck(mock_registry, mock_backend):
    state = {"Running": True, "Status": "running"}
    mock_backend.set_response("docker", CommandResult(returncode=0, stdout=json.dumps(state), stderr=""))

    out = await wait_for_state(
        "docker_container",
        "nginx",
        "healthy",
        interval_seconds=1,
        timeout_seconds=5,
        tool_context=_FakeToolContext(),
    )
    assert "no health check" in out.lower()


@pytest.mark.asyncio
async def test_background_registers_task(mock_registry, mock_backend):
    """With a sink, the tool returns immediately and completes asynchronously."""
    state = {"Running": True, "Status": "running", "ExitCode": 0}
    mock_backend.set_response("docker", CommandResult(returncode=0, stdout=json.dumps(state), stderr=""))

    delivered: list[tuple[str, str]] = []

    class _Sink:
        use_background = True

        async def deliver_monitor_result(self, monitor_id: str, content: str) -> None:
            delivered.append((monitor_id, content))

    sid = _FakeToolContext.session.id
    register_monitor_session_sink(sid, _Sink())
    try:
        out = await wait_for_state(
            "docker_container",
            "web",
            "running",
            interval_seconds=1,
            timeout_seconds=5,
            tool_context=_FakeToolContext(),
        )
        assert "Monitor" in out
        assert "started" in out.lower()

        for _ in range(50):
            if delivered:
                break
            await asyncio.sleep(0.05)
    finally:
        unregister_monitor_session_sink(sid)

    assert len(delivered) == 1
    assert "web" in delivered[0][1].lower()


@pytest.mark.asyncio
async def test_invalid_kind(mock_registry):
    out = await wait_for_state(
        "not_a_kind",
        "x",
        "running",
        tool_context=_FakeToolContext(),
    )
    assert "Unsupported" in out
