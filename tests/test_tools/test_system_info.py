"""Tests for system_info tool with mocked backend."""

import json
from unittest.mock import patch

import pytest

from squire.system.backend import CommandResult
from squire.tools import system_info


@pytest.mark.asyncio
@patch("squire.tools.system_info.platform")
async def test_system_info_basic(mock_platform, mock_backend, mock_registry):
    """system_info should return valid JSON with expected fields."""
    mock_platform.system.return_value = "Darwin"
    mock_platform.node.return_value = "test-host"
    mock_platform.release.return_value = "23.0.0"
    mock_platform.machine.return_value = "arm64"
    mock_backend.set_response("sysctl", CommandResult(returncode=0, stdout="8\n", stderr=""))
    mock_backend.set_response("ps", CommandResult(returncode=0, stdout="%CPU\n10.0\n5.0\n", stderr=""))
    mock_backend.set_response(
        "vm_stat",
        CommandResult(
            returncode=0,
            stdout="Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:  100000.\n",
            stderr="",
        ),
    )
    mock_backend.set_response(
        "df",
        CommandResult(
            returncode=0,
            stdout="/dev/disk1s1  500G  200G  300G  40%  /\n",
            stderr="",
        ),
    )
    mock_backend.set_response(
        "uptime",
        CommandResult(
            returncode=0,
            stdout="up 5 days\n",
            stderr="",
        ),
    )

    result = await system_info()
    data = json.loads(result)

    assert "hostname" in data
    assert "os" in data
    assert data["cpu_percent"] == 15.0
    assert data["uptime"] == "up 5 days"


@pytest.mark.asyncio
async def test_system_info_remote_host(mock_backend, mock_registry):
    """system_info with a remote host should use uname instead of platform."""
    mock_backend.os_type = "Linux"
    mock_backend.set_response(
        "hostname",
        CommandResult(
            returncode=0,
            stdout="media-server\n",
            stderr="",
        ),
    )
    mock_backend.set_response(
        "uname",
        CommandResult(
            returncode=0,
            stdout="Linux 6.1.0\n",
            stderr="",
        ),
    )
    mock_backend.set_response(
        "nproc",
        CommandResult(
            returncode=0,
            stdout="4\n",
            stderr="",
        ),
    )
    mock_backend.set_response(
        "grep",
        CommandResult(
            returncode=0,
            stdout="cpu  1000 200 300 500 100 50 20 0 0 0\n",
            stderr="",
        ),
    )
    free_stdout = "              total        used        free\nMem:          16384        8192        8192\n"
    mock_backend.set_response(
        "free",
        CommandResult(
            returncode=0,
            stdout=free_stdout,
            stderr="",
        ),
    )
    mock_backend.set_response(
        "df",
        CommandResult(
            returncode=0,
            stdout="/dev/sda1  100G  50G  50G  50%  /\n",
            stderr="",
        ),
    )
    mock_backend.set_response(
        "uptime",
        CommandResult(
            returncode=0,
            stdout="up 30 days\n",
            stderr="",
        ),
    )

    result = await system_info(host="media-server")
    data = json.loads(result)

    assert data["hostname"] == "media-server"
    assert data["uptime"] == "up 30 days"
