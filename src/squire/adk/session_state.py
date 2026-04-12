"""Session-state builders for ADK chat and watch flows."""

from agent_risk_engine import RuleGate


def _base_state(
    *,
    latest_snapshot: dict[str, dict],
    available_hosts: list[str],
    host_configs: dict[str, dict],
    risk_tolerance: int,
    risk_strict: bool,
    risk_allowed_tools: set[str],
    risk_approval_tools: set[str],
    risk_denied_tools: set[str],
) -> dict:
    return {
        "latest_snapshot": latest_snapshot,
        "available_hosts": list(available_hosts),
        "host_configs": host_configs,
        # Keep risk state JSON-safe so durable ADK sessions can persist it.
        "risk_tolerance": RuleGate(threshold=risk_tolerance).threshold,
        "risk_strict": bool(risk_strict),
        "risk_allowed_tools": sorted(risk_allowed_tools),
        "risk_approval_tools": sorted(risk_approval_tools),
        "risk_denied_tools": sorted(risk_denied_tools),
    }


def build_chat_session_state(
    *,
    latest_snapshot: dict[str, dict],
    available_hosts: list[str],
    host_configs: dict[str, dict],
    risk_tolerance: int,
    risk_strict: bool,
    risk_allowed_tools: set[str],
    risk_approval_tools: set[str],
    risk_denied_tools: set[str],
) -> dict:
    """Build serializable state for interactive chat sessions."""
    return _base_state(
        latest_snapshot=latest_snapshot,
        available_hosts=available_hosts,
        host_configs=host_configs,
        risk_tolerance=risk_tolerance,
        risk_strict=risk_strict,
        risk_allowed_tools=risk_allowed_tools,
        risk_approval_tools=risk_approval_tools,
        risk_denied_tools=risk_denied_tools,
    )


def build_watch_session_state(
    *,
    latest_snapshot: dict[str, dict],
    available_hosts: list[str],
    host_configs: dict[str, dict],
    risk_tolerance: int,
    risk_allowed_tools: set[str],
    risk_denied_tools: set[str],
) -> dict:
    """Build serializable state for headless watch sessions."""
    state = _base_state(
        latest_snapshot=latest_snapshot,
        available_hosts=available_hosts,
        host_configs=host_configs,
        risk_tolerance=risk_tolerance,
        risk_strict=True,
        risk_allowed_tools=risk_allowed_tools,
        risk_approval_tools=set(),
        risk_denied_tools=risk_denied_tools,
    )
    state["watch_mode"] = True
    return state
