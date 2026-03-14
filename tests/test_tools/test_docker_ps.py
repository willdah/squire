"""Tests for docker_ps tool with mocked backend."""

import sys

import pytest

from squire.system.backend import CommandResult
from squire.tools import docker_ps

# Get the actual module (not the function re-exported by __init__.py)
_mod = sys.modules["squire.tools.docker_ps"]


@pytest.mark.asyncio
async def test_docker_ps_table(mock_backend, monkeypatch):
    monkeypatch.setattr(_mod, "_backend", mock_backend)
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="NAMES    STATUS    IMAGE\nnginx    Up 2h     nginx:latest\n",
        stderr="",
    ))

    result = await docker_ps(format="table")
    assert "nginx" in result


@pytest.mark.asyncio
async def test_docker_ps_json(mock_backend, monkeypatch):
    monkeypatch.setattr(_mod, "_backend", mock_backend)
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout='{"Names":"nginx","Status":"Up 2h","Image":"nginx:latest","State":"running","Ports":"80/tcp"}\n',
        stderr="",
    ))

    result = await docker_ps(format="json")
    assert "nginx" in result


@pytest.mark.asyncio
async def test_docker_ps_not_installed(mock_backend, monkeypatch):
    monkeypatch.setattr(_mod, "_backend", mock_backend)
    mock_backend.set_response("docker", CommandResult(
        returncode=1,
        stdout="",
        stderr="docker: command not found",
    ))

    result = await docker_ps()
    assert result  # Should return something, not crash
