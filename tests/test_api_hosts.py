"""Tests for the /api/hosts/{name}/verify endpoint — checked_at behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from squire.api.routers.hosts import verify_host


@pytest.fixture(autouse=True)
async def _reset_snapshot_cache():
    """Keep tests independent by emptying the module-level snapshot cache."""
    from squire.api import app as api_app

    await api_app.set_latest_snapshot({})
    yield
    await api_app.set_latest_snapshot({})


@pytest.mark.asyncio
async def test_verify_success_returns_checked_at_and_updates_cache():
    from squire.api import app as api_app

    host_store = SimpleNamespace(verify=AsyncMock(return_value=True))
    fresh_snap = {
        "hostname": "srv",
        "containers": [],
        "checked_at": "2026-04-18T12:00:00+00:00",
    }
    with patch("squire.main._collect_snapshot", new=AsyncMock(return_value=fresh_snap)):
        resp = await verify_host("srv", host_store=host_store)

    assert resp.reachable is True
    assert resp.checked_at == "2026-04-18T12:00:00+00:00"
    cache = await api_app.get_latest_snapshot()
    assert cache["srv"]["checked_at"] == "2026-04-18T12:00:00+00:00"
    assert cache["srv"].get("error") is None


@pytest.mark.asyncio
async def test_verify_failure_writes_unreachable_snapshot():
    from squire.api import app as api_app

    # Pre-seed the cache with a stale "healthy" snapshot — a failed verify
    # must overwrite it rather than leave it in place.
    await api_app.set_latest_snapshot(
        {"srv": {"hostname": "srv", "containers": [], "checked_at": "2026-04-18T10:00:00+00:00"}}
    )

    host_store = SimpleNamespace(verify=AsyncMock(return_value=False))
    resp = await verify_host("srv", host_store=host_store)

    assert resp.reachable is False
    assert resp.checked_at  # populated
    cache = await api_app.get_latest_snapshot()
    assert cache["srv"]["error"] == "unreachable"
    assert cache["srv"]["checked_at"] == resp.checked_at
    assert cache["srv"]["checked_at"] != "2026-04-18T10:00:00+00:00"
