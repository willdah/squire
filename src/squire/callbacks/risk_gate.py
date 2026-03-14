"""Risk gate callback — enforces risk profiles on tool execution.

Wired into the ADK Agent as a before_tool_callback. Checks the active
risk profile and either allows, blocks, or requests approval for each
tool invocation.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from ..schemas.risk import GateResult, RiskProfile
from ..tools import TOOL_RISK_LEVELS
from ..tui.approval_bridge import approval_bridge


async def risk_gate_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict | None:
    """ADK before_tool_callback that enforces the active risk profile.

    Signature: Callable[[BaseTool, dict[str, Any], ToolContext], Optional[dict]]

    Args:
        tool: The ADK BaseTool instance about to be executed.
        args: Arguments that will be passed to the tool.
        tool_context: ADK ToolContext with access to session state.

    Returns:
        None to allow execution, or a dict response to block it.
    """
    tool_name = tool.name
    risk_level = TOOL_RISK_LEVELS.get(tool_name, "full")

    # Load risk profile from session state
    profile_data = tool_context.state.get("risk_profile")
    if not profile_data:
        profile = RiskProfile(name="cautious")
    elif isinstance(profile_data, dict):
        profile = RiskProfile.model_validate(profile_data)
    else:
        profile = profile_data

    gate_result = profile.gate(tool_name, risk_level)

    if gate_result == GateResult.DENIED:
        return {"error": f"Blocked: '{tool_name}' is denied by the '{profile.name}' risk profile."}

    if gate_result == GateResult.NEEDS_APPROVAL:
        approved = approval_bridge.request_approval(tool_name, args, risk_level)
        if not approved:
            return {"error": f"User declined to approve '{tool_name}'."}

    # GateResult.ALLOWED — proceed
    return None
