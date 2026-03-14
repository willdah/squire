"""Tests for run_command tool with mocked backend."""

import sys

import pytest

from squire.config import PathsConfig
from squire.system.backend import CommandResult
from squire.tools import run_command

_mod = sys.modules["squire.tools.run_command"]


@pytest.mark.asyncio
async def test_allowed_command(mock_backend, monkeypatch):
    monkeypatch.setattr(_mod, "_backend", mock_backend)
    monkeypatch.setattr(_mod, "_paths_config", PathsConfig())
    mock_backend.set_response("ping", CommandResult(returncode=0, stdout="PING ok\n", stderr=""))

    result = await run_command("ping -c 1 localhost")
    assert "PING ok" in result


@pytest.mark.asyncio
async def test_denied_command():
    result = await run_command("rm -rf /")
    assert "Blocked" in result or "denylist" in result


@pytest.mark.asyncio
async def test_unlisted_command():
    result = await run_command("curl http://example.com")
    assert "not on the allowlist" in result


@pytest.mark.asyncio
async def test_empty_command():
    result = await run_command("")
    assert "Empty" in result or "Invalid" in result


@pytest.mark.asyncio
async def test_invalid_syntax():
    result = await run_command("echo 'unclosed")
    assert "Invalid" in result or "syntax" in result.lower()
