"""Tests for session history API endpoints."""

from types import SimpleNamespace

import pytest

from squire.api.routers.sessions import delete_all_sessions, delete_session
from squire.database.service import DatabaseService


async def _seed_session(db: DatabaseService, session_id: str) -> None:
    await db.create_session(session_id)
    await db.save_message(session_id=session_id, role="user", content="hi")


@pytest.mark.asyncio
async def test_delete_session_also_deletes_adk_state(db):
    class _SessionService:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
            self.deleted.append(session_id)

    session_service = _SessionService()
    adk_runtime = SimpleNamespace(session_service=session_service)
    app_config = SimpleNamespace(app_name="Squire", user_id="squire-user")

    await _seed_session(db, "sess-1")
    resp = await delete_session("sess-1", db=db, app_config=app_config, adk_runtime=adk_runtime)
    assert resp == {"deleted": True}
    assert session_service.deleted == ["sess-1"]


@pytest.mark.asyncio
async def test_delete_all_sessions_also_deletes_adk_state(db):
    class _SessionService:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
            self.deleted.append(session_id)

    session_service = _SessionService()
    adk_runtime = SimpleNamespace(session_service=session_service)
    app_config = SimpleNamespace(app_name="Squire", user_id="squire-user")

    await _seed_session(db, "sess-a")
    await _seed_session(db, "sess-b")
    resp = await delete_all_sessions(db=db, app_config=app_config, adk_runtime=adk_runtime)
    assert resp == {"deleted": 2}
    assert sorted(session_service.deleted) == ["sess-a", "sess-b"]
