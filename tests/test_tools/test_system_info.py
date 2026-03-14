"""Tests for system_info tool with mocked backend."""

import json
import sys

import pytest

from squire.system.backend import CommandResult
from squire.tools import system_info

_mod = sys.modules["squire.tools.system_info"]


@pytest.mark.asyncio
async def test_system_info_basic(mock_backend, monkeypatch):
    """system_info should return valid JSON with expected fields."""
    monkeypatch.setattr(_mod, "_backend", mock_backend)

    mock_backend.set_response("sysctl", CommandResult(returncode=0, stdout="8\n", stderr=""))
    mock_backend.set_response("ps", CommandResult(returncode=0, stdout="%CPU\n10.0\n5.0\n", stderr=""))
    mock_backend.set_response("vm_stat", CommandResult(
        returncode=0,
        stdout="Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:  100000.\n",
        stderr="",
    ))
    mock_backend.set_response("df", CommandResult(returncode=0, stdout="/dev/disk1s1  500G  200G  300G  40%  /\n", stderr=""))
    mock_backend.set_response("uptime", CommandResult(returncode=0, stdout="up 5 days\n", stderr=""))

    result = await system_info()
    data = json.loads(result)

    assert "hostname" in data
    assert "os" in data
    assert data["cpu_percent"] == 15.0
    assert data["uptime"] == "up 5 days"
