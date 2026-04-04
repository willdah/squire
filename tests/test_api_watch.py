"""Tests for watch mode REST API endpoints."""

import json

import pytest
import pytest_asyncio

from squire.database.service import DatabaseService


@pytest_asyncio.fixture
async def db(tmp_path):
    db = DatabaseService(tmp_path / "test.db")
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_watch_status(db):
    from squire.api.routers.watch import watch_status

    await db.set_watch_state("status", "running")
    await db.set_watch_state("cycle", "5")
    result = await watch_status(db=db)
    assert result.status == "running"
    assert result.cycle == "5"


@pytest.mark.asyncio
async def test_watch_stop(db):
    from squire.api.routers.watch import watch_stop

    result = await watch_stop(db=db)
    assert result.status == "ok"

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 1
    assert pending[0]["command"] == "stop"


@pytest.mark.asyncio
async def test_watch_config_update(db):
    from squire.api.routers.watch import watch_config_update
    from squire.api.schemas import WatchConfigUpdate

    update = WatchConfigUpdate(interval_minutes=1, checkin_prompt="Custom prompt")
    result = await watch_config_update(update=update, db=db)
    assert result.status == "ok"

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 1
    payload = json.loads(pending[0]["payload"])
    assert payload["interval_minutes"] == 1
    assert payload["checkin_prompt"] == "Custom prompt"


@pytest.mark.asyncio
async def test_watch_cycles(db):
    from squire.api.routers.watch import watch_cycles

    await db.insert_watch_event(1, "cycle_start", json.dumps({"session_id": "s1"}))
    await db.insert_watch_event(1, "cycle_end", json.dumps({"status": "ok", "duration_seconds": 5, "tool_count": 2}))

    result = await watch_cycles(page=1, per_page=10, db=db)
    assert len(result) == 1
    assert result[0]["cycle"] == 1


@pytest.mark.asyncio
async def test_watch_cycle_detail(db):
    from squire.api.routers.watch import watch_cycle_detail

    await db.insert_watch_event(1, "cycle_start", "{}")
    await db.insert_watch_event(1, "token", "hello")
    await db.insert_watch_event(1, "cycle_end", "{}")

    result = await watch_cycle_detail(cycle=1, db=db)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_watch_approve(db):
    from squire.api.routers.watch import watch_approve
    from squire.api.schemas import WatchApprovalAction

    await db.insert_watch_approval(request_id="req-1", tool_name="test", args="{}", risk_level=3)

    result = await watch_approve(request_id="req-1", action=WatchApprovalAction(approved=True), db=db)
    assert result.status == "ok"

    approval = await db.get_watch_approval("req-1")
    assert approval["status"] == "approved"


@pytest.mark.asyncio
async def test_watch_approve_already_resolved(db):
    from fastapi import HTTPException

    from squire.api.routers.watch import watch_approve
    from squire.api.schemas import WatchApprovalAction

    await db.insert_watch_approval(request_id="req-1", tool_name="test", args="{}", risk_level=3)
    await db.update_watch_approval("req-1", "approved")

    with pytest.raises(HTTPException) as exc_info:
        await watch_approve(request_id="req-1", action=WatchApprovalAction(approved=True), db=db)
    assert exc_info.value.status_code == 409
