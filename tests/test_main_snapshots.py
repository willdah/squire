"""Tests for _collect_snapshot — checked_at timestamp and unreachable flag."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from squire.main import _collect_snapshot


@pytest.fixture
def mock_system_info_ok():
    payload = json.dumps(
        {
            "hostname": "box",
            "os": "Linux 6.0",
            "cpu_percent": 1.0,
            "memory_total_mb": 1024,
            "memory_used_mb": 256,
            "uptime": "1d",
            "disk_usage": "50%",
        }
    )
    with patch("squire.main.system_info", new=AsyncMock(return_value=payload)) as m:
        yield m


@pytest.fixture
def mock_docker_ps_ok():
    with patch("squire.main.docker_ps", new=AsyncMock(return_value="")) as m:
        yield m


@pytest.fixture
def mock_probe_ok():
    with patch("squire.main._probe_reachable", new=AsyncMock(return_value=True)) as m:
        yield m


@pytest.fixture
def mock_probe_fail():
    with patch("squire.main._probe_reachable", new=AsyncMock(return_value=False)) as m:
        yield m


@pytest.mark.asyncio
async def test_snapshot_has_checked_at_and_no_error_on_success(mock_system_info_ok, mock_docker_ps_ok, mock_probe_ok):
    snap = await _collect_snapshot(host="box")
    assert "checked_at" in snap and snap["checked_at"]
    assert snap.get("error") is None
    assert snap["hostname"] == "box"


@pytest.mark.asyncio
async def test_snapshot_short_circuits_when_probe_fails(mock_probe_fail):
    # The probe guards against system_info silently returning stub data
    # when SSH is refused — SSHBackend.run catches connection errors and
    # returns returncode=-1 rather than raising.
    snap = await _collect_snapshot(host="dead")
    assert snap["error"] == "unreachable"
    assert "checked_at" in snap and snap["checked_at"]
    assert snap["hostname"] == "dead"
    assert snap["containers"] == []


@pytest.mark.asyncio
async def test_snapshot_marks_unreachable_when_system_info_fails(mock_docker_ps_ok, mock_probe_ok):
    with patch("squire.main.system_info", new=AsyncMock(side_effect=OSError("no route"))):
        snap = await _collect_snapshot(host="dead")
    assert snap["error"] == "unreachable"
    assert "checked_at" in snap and snap["checked_at"]
    assert snap["hostname"] == "dead"


@pytest.mark.asyncio
async def test_snapshot_not_unreachable_when_only_docker_fails(mock_system_info_ok, mock_probe_ok):
    # docker_ps failing alone should not be treated as unreachable —
    # the host may simply not have Docker installed.
    with patch("squire.main.docker_ps", new=AsyncMock(side_effect=OSError("no docker"))):
        snap = await _collect_snapshot(host="box")
    assert snap.get("error") is None
    assert snap["containers"] == []
    assert "checked_at" in snap and snap["checked_at"]


@pytest.mark.asyncio
async def test_local_host_skips_probe(mock_system_info_ok, mock_docker_ps_ok):
    # Local host does not need the reachability probe — local commands
    # never go through SSH so the probe would be wasted cost.
    with patch("squire.main._probe_reachable", new=AsyncMock(side_effect=AssertionError("probed local"))):
        snap = await _collect_snapshot(host="local")
    assert snap.get("error") is None
    assert "checked_at" in snap
