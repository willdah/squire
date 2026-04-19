"""Tests for the shared ADK runtime wrapper."""

import pytest

from squire.adk.runtime import AdkRuntime
from squire.adk.session_state import build_chat_session_state, build_watch_session_state


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


def test_runtime_resolves_dedicated_adk_session_db_path(tmp_path):
    base = tmp_path / "squire.db"
    resolved = AdkRuntime._resolve_session_db_path(base)
    assert resolved.name == "squire.adk_sessions.db"


def test_runtime_resolves_path_without_suffix(tmp_path):
    base = tmp_path / "squiredb"
    resolved = AdkRuntime._resolve_session_db_path(base)
    assert resolved.name == "squiredb.adk_sessions.db"


def test_chat_session_state_builder_is_json_safe():
    state = build_chat_session_state(
        latest_snapshot={"local": {"cpu_percent": 10}},
        available_hosts=["local", "nas"],
        host_configs={"local": {"name": "local"}},
        risk_tolerance=3,
        risk_strict=False,
        risk_allowed_tools={"system_info"},
        risk_approval_tools={"run_command"},
        risk_denied_tools={"docker_container:remove"},
    )
    assert state["risk_tolerance"] == 3
    assert state["risk_strict"] is False
    assert state["risk_allowed_tools"] == ["system_info"]
    assert state["risk_approval_tools"] == ["run_command"]
    assert state["risk_denied_tools"] == ["docker_container:remove"]


def test_watch_session_state_builder_sets_watch_mode():
    state = build_watch_session_state(
        latest_snapshot={"local": {"cpu_percent": 10}},
        available_hosts=["local"],
        host_configs={"local": {"name": "local"}},
        risk_tolerance=4,
        risk_allowed_tools={"system_info"},
        risk_approval_tools=set(),
        risk_denied_tools={"run_command"},
    )
    assert state["watch_mode"] is True
    assert state["risk_tolerance"] == 4
    assert state["risk_strict"] is True
