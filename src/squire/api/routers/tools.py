"""Tool catalog endpoint — introspects the tool registry and merges guardrails."""

import inspect

from fastapi import APIRouter, Depends

from ...config import GuardrailsConfig
from ...tools import TOOL_RISK_LEVELS

# Import raw tool functions for signature introspection
from ...tools.docker_cleanup import docker_cleanup
from ...tools.docker_compose import docker_compose
from ...tools.docker_container import docker_container
from ...tools.docker_image import docker_image
from ...tools.docker_logs import docker_logs
from ...tools.docker_ps import docker_ps
from ...tools.groups import ADMIN_TOOL_NAMES, CONTAINER_TOOL_NAMES, MONITOR_TOOL_NAMES
from ...tools.journalctl import journalctl
from ...tools.network_info import network_info
from ...tools.read_config import read_config
from ...tools.run_command import run_command
from ...tools.system_info import system_info
from ...tools.systemctl import systemctl
from ...tools.wait_for_state import wait_for_state
from ..dependencies import get_guardrails
from ..schemas import ToolAction, ToolInfo, ToolParameter

router = APIRouter()

# Ordered list of (name, function) for deterministic output
_TOOL_ENTRIES: list[tuple[str, object]] = [
    ("system_info", system_info),
    ("network_info", network_info),
    ("docker_ps", docker_ps),
    ("docker_logs", docker_logs),
    ("docker_compose", docker_compose),
    ("docker_container", docker_container),
    ("docker_image", docker_image),
    ("docker_cleanup", docker_cleanup),
    ("read_config", read_config),
    ("journalctl", journalctl),
    ("systemctl", systemctl),
    ("run_command", run_command),
    ("wait_for_state", wait_for_state),
]


def _get_group(tool_name: str) -> str:
    """Map a tool name to its agent group."""
    if tool_name in MONITOR_TOOL_NAMES:
        return "monitor"
    if tool_name in CONTAINER_TOOL_NAMES:
        return "container"
    if tool_name in ADMIN_TOOL_NAMES:
        return "admin"
    return "other"


def _extract_parameters(func: object) -> list[ToolParameter]:
    """Extract parameter metadata from a tool function's signature."""
    sig = inspect.signature(func)
    params = []
    for name, param in sig.parameters.items():
        if name == "tool_context":
            continue
        hint = param.annotation
        if hint is inspect.Parameter.empty:
            type_name = "str"
        elif hasattr(hint, "__name__"):
            type_name = hint.__name__
        else:
            type_name = str(hint).replace("typing.", "")
        params.append(
            ToolParameter(
                name=name,
                type=type_name,
                required=param.default is inspect.Parameter.empty,
                default=str(param.default) if param.default is not inspect.Parameter.empty else None,
            )
        )
    return params


def _get_action_names(tool_name: str) -> list[str]:
    """Return action names for a multi-action tool, or empty list for single-action."""
    prefix = f"{tool_name}:"
    return [key.split(":", 1)[1] for key in TOOL_RISK_LEVELS if key.startswith(prefix)]


def _build_tool_catalog(guardrails: GuardrailsConfig) -> list[ToolInfo]:
    """Build the full tool catalog, merging registry data with guardrails config."""
    tools: list[ToolInfo] = []
    denied = set(guardrails.tools_deny)
    allowed = set(guardrails.tools_allow)
    require_approval = set(guardrails.tools_require_approval)
    overrides = guardrails.tools_risk_overrides

    for name, func in _TOOL_ENTRIES:
        params = _extract_parameters(func)
        description = func.__doc__.strip().split("\n")[0] if func.__doc__ else ""
        group = _get_group(name)
        status = "disabled" if name in denied else "enabled"

        # Determine approval policy
        approval_policy: str | None = None
        if name in require_approval:
            approval_policy = "always"
        elif name in allowed:
            approval_policy = "never"

        action_names = _get_action_names(name)

        if action_names:
            actions = [
                ToolAction(
                    name=action,
                    risk_level=TOOL_RISK_LEVELS.get(f"{name}:{action}", 1),
                    risk_override=overrides.get(f"{name}:{action}"),
                )
                for action in action_names
            ]
            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    group=group,
                    parameters=params,
                    actions=actions,
                    status=status,
                    approval_policy=approval_policy,
                )
            )
        else:
            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    group=group,
                    parameters=params,
                    risk_level=TOOL_RISK_LEVELS.get(name, 1),
                    risk_override=overrides.get(name),
                    status=status,
                    approval_policy=approval_policy,
                )
            )
    return tools


@router.get("", response_model=list[ToolInfo])
def list_tools(guardrails: GuardrailsConfig = Depends(get_guardrails)):
    """List all available tools with their metadata and effective configuration."""
    return _build_tool_catalog(guardrails)
