"""Tests for the shared ADK runtime wrapper."""

import pytest

from squire.adk.runtime import AdkRuntime


@pytest.mark.asyncio
async def test_runtime_reuses_sqlite_sessions_across_instances(tmp_path):
    db_path = tmp_path / "adk-sessions.db"
    runtime_a = AdkRuntime(app_name="Squire", db_path=db_path)
    session = await runtime_a.get_or_create_session(
        app_name="Squire",
        user_id="user-1",
        session_id="session-1",
        state={"risk_tolerance": 3},
    )
    assert session.id == "session-1"

    runtime_b = AdkRuntime(app_name="Squire", db_path=db_path)
    existing = await runtime_b.session_service.get_session(
        app_name="Squire",
        user_id="user-1",
        session_id="session-1",
    )
    assert existing is not None
    assert existing.id == "session-1"
