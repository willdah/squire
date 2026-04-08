"""Tests for run_command tool with mocked backend."""

import sys

import pytest

from squire.config import GuardrailsConfig
from squire.system.backend import CommandResult
from squire.tools import run_command

_mod = sys.modules["squire.tools.run_command"]


@pytest.mark.asyncio
async def test_allowed_command(mock_backend, mock_registry, monkeypatch):
    monkeypatch.setattr(_mod, "_guardrails_config", GuardrailsConfig())
    mock_backend.set_response("bash", CommandResult(returncode=0, stdout="PING ok\n", stderr=""))

    result = await run_command("ping -c 1 localhost")
    assert "PING ok" in result


@pytest.mark.asyncio
async def test_denied_command(monkeypatch):
    config = GuardrailsConfig(commands_block=["rm"], commands_allow=[])
    monkeypatch.setattr(_mod, "_guardrails_config", config)
    result = await run_command("rm -rf /")
    assert "DENIED" in result


@pytest.mark.asyncio
async def test_unlisted_command(monkeypatch):
    config = GuardrailsConfig(commands_allow=["ping"], commands_block=[])
    monkeypatch.setattr(_mod, "_guardrails_config", config)
    result = await run_command("curl http://example.com")
    assert "DENIED" in result


@pytest.mark.asyncio
async def test_empty_command():
    result = await run_command("")
    assert "Empty" in result


@pytest.mark.asyncio
async def test_run_command_with_host_param(mock_backend, mock_registry, monkeypatch):
    """The host parameter should be accepted."""
    monkeypatch.setattr(_mod, "_guardrails_config", GuardrailsConfig())
    mock_backend.set_response("bash", CommandResult(returncode=0, stdout="PING ok\n", stderr=""))

    result = await run_command("ping -c 1 localhost", host="local")
    assert "PING ok" in result


@pytest.mark.asyncio
async def test_shell_metacharacters(mock_backend, mock_registry, monkeypatch):
    """Semicolons, pipes, and chained commands should work via bash -c."""
    monkeypatch.setattr(_mod, "_guardrails_config", GuardrailsConfig())
    mock_backend.set_response("bash", CommandResult(returncode=0, stdout="done\n", stderr=""))

    result = await run_command("ls; sleep 1; echo done")
    assert "done" in result


@pytest.mark.asyncio
async def test_denied_with_semicolon(monkeypatch):
    """Blocklist still catches the base command even with shell syntax."""
    config = GuardrailsConfig(commands_block=["rm"], commands_allow=[])
    monkeypatch.setattr(_mod, "_guardrails_config", config)
    result = await run_command("rm -rf /; echo hacked")
    assert "DENIED" in result
