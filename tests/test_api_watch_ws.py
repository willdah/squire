"""Tests for watch mode WebSocket supervisor tracking."""

import pytest
import pytest_asyncio

from squire.database.service import DatabaseService


@pytest_asyncio.fixture
async def db(tmp_path):
    db = DatabaseService(tmp_path / "test.db")
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_ws_sets_supervisor_connected(db):
    """Verify supervisor tracking logic."""
    from squire.api.routers.watch import _increment_supervisor_count, _decrement_supervisor_count

    await _increment_supervisor_count(db)
    assert await db.get_watch_state("supervisor_connected") == "true"
    assert await db.get_watch_state("supervisor_count") == "1"

    await _increment_supervisor_count(db)
    assert await db.get_watch_state("supervisor_count") == "2"

    await _decrement_supervisor_count(db)
    assert await db.get_watch_state("supervisor_connected") == "true"
    assert await db.get_watch_state("supervisor_count") == "1"

    await _decrement_supervisor_count(db)
    assert await db.get_watch_state("supervisor_connected") == "false"
    assert await db.get_watch_state("supervisor_count") == "0"
