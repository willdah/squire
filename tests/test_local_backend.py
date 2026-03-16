"""Tests for LocalBackend error handling."""

from unittest.mock import AsyncMock, patch

import pytest

from squire.system.local import LocalBackend


@pytest.mark.asyncio
async def test_file_not_found():
    """FileNotFoundError from create_subprocess_exec → CommandResult with 'not found'."""
    backend = LocalBackend()
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("journalctl")):
        result = await backend.run(["journalctl", "-n", "50"])
    assert result.returncode == -1
    assert "Command not found" in result.stderr
    assert "journalctl" in result.stderr


@pytest.mark.asyncio
async def test_permission_error():
    """PermissionError from create_subprocess_exec → CommandResult with 'denied'."""
    backend = LocalBackend()
    with patch("asyncio.create_subprocess_exec", side_effect=PermissionError("restricted")):
        result = await backend.run(["restricted-cmd"])
    assert result.returncode == -1
    assert "Permission denied" in result.stderr
    assert "restricted-cmd" in result.stderr


@pytest.mark.asyncio
async def test_os_error():
    """Generic OSError from create_subprocess_exec → CommandResult with error message."""
    backend = LocalBackend()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("bad fd")):
        result = await backend.run(["broken"])
    assert result.returncode == -1
    assert "Failed to execute broken" in result.stderr
    assert "bad fd" in result.stderr


@pytest.mark.asyncio
async def test_timeout_still_works():
    """Timeout handling continues to work after the error handling changes."""
    backend = LocalBackend()
    proc = AsyncMock()
    proc.returncode = -1
    proc.kill = AsyncMock()
    # communicate() after kill returns empty output
    proc.communicate = AsyncMock(return_value=(b"", b""))

    async def fake_wait_for(coro, *, timeout):
        # Consume the coroutine to avoid RuntimeWarning
        coro.close()
        raise TimeoutError

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch("asyncio.wait_for", side_effect=fake_wait_for):
            result = await backend.run(["sleep", "999"], timeout=0.1)
    assert result.returncode == -1
    assert "timed out" in result.stderr


@pytest.mark.asyncio
async def test_successful_command():
    """Normal command execution still returns proper output."""
    backend = LocalBackend()
    proc = AsyncMock()
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch("asyncio.wait_for", return_value=(b"hello\n", b"")):
            result = await backend.run(["echo", "hello"])
    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
