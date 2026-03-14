"""Tests for systemctl tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools import systemctl


@pytest.mark.asyncio
async def test_allowed_action_status(mock_backend, mock_registry):
    mock_backend.set_response("systemctl", CommandResult(
        returncode=0,
        stdout="● caddy.service - Caddy\n   Active: active (running)\n",
        stderr="",
    ))

    result = await systemctl(action="status", unit="caddy")
    assert "caddy" in result.lower()


@pytest.mark.asyncio
async def test_allowed_action_restart(mock_backend, mock_registry):
    mock_backend.set_response("systemctl", CommandResult(
        returncode=0,
        stdout="",
        stderr="",
    ))

    result = await systemctl(action="restart", unit="caddy")
    assert "completed" in result


@pytest.mark.asyncio
async def test_disallowed_action():
    result = await systemctl(action="enable", unit="caddy")
    assert "Invalid action" in result


@pytest.mark.asyncio
async def test_no_pager_on_status(mock_backend, mock_registry):
    """Status action should include --no-pager flag."""
    calls = []

    async def capture_run(cmd, *, timeout=30.0):
        calls.append(cmd)
        return CommandResult(returncode=0, stdout="active\n", stderr="")

    mock_backend.run = capture_run

    await systemctl(action="status", unit="caddy")
    assert "--no-pager" in calls[0]


@pytest.mark.asyncio
async def test_no_pager_absent_on_restart(mock_backend, mock_registry):
    """Non-status actions should not include --no-pager."""
    calls = []

    async def capture_run(cmd, *, timeout=30.0):
        calls.append(cmd)
        return CommandResult(returncode=0, stdout="", stderr="")

    mock_backend.run = capture_run

    await systemctl(action="restart", unit="caddy")
    assert "--no-pager" not in calls[0]


@pytest.mark.asyncio
async def test_host_parameter(mock_backend, mock_registry):
    """The host parameter should be accepted."""
    mock_backend.set_response("systemctl", CommandResult(
        returncode=0,
        stdout="active\n",
        stderr="",
    ))

    result = await systemctl(action="is-active", unit="caddy", host="local")
    assert "active" in result


@pytest.mark.asyncio
async def test_inactive_service_status(mock_backend, mock_registry):
    """systemctl status returns exit code 3 for inactive services but still has useful output."""
    mock_backend.set_response("systemctl", CommandResult(
        returncode=3,
        stdout="● caddy.service - Caddy\n   Active: inactive (dead)\n",
        stderr="",
    ))

    result = await systemctl(action="status", unit="caddy")
    assert "inactive" in result
