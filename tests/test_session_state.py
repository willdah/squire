"""Tests for ADK session-state builders."""

from squire.adk.session_state import build_watch_session_state


def test_watch_session_state_includes_risk_approval_tools():
    state = build_watch_session_state(
        latest_snapshot={},
        available_hosts=["local"],
        host_configs={},
        risk_tolerance=3,
        risk_allowed_tools={"system_info"},
        risk_approval_tools={"run_command"},
        risk_denied_tools={"docker_container"},
    )
    assert state["risk_approval_tools"] == ["run_command"]
