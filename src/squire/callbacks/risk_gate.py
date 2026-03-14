"""Risk gate callback — ADK adapter for the risk evaluation pipeline.

Wired into the ADK Agent as a before_tool_callback. Translates between
the framework-agnostic RiskEvaluator and ADK's callback signature.
"""

from __future__ import annotations

from typing import Any

from agent_risk_engine import GateResult, RiskEvaluator, RuleGate
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from ..tools import TOOL_RISK_LEVELS
from ..tui.approval_bridge import approval_bridge


async def risk_gate_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict | None:
    """ADK before_tool_callback that runs the risk evaluation pipeline.

    Args:
        tool: The ADK BaseTool instance about to be executed.
        args: Arguments that will be passed to the tool.
        tool_context: ADK ToolContext with access to session state.

    Returns:
        None to allow execution, or a dict response to block it.
    """
    tool_name = tool.name
    tool_risk = TOOL_RISK_LEVELS.get(tool_name, 5)

    # Bump risk for remote host operations
    host = args.get("host", "local")
    if host != "local":
        tool_risk = min(tool_risk + 1, 5)

    # Load the risk evaluator from session state
    evaluator = tool_context.state.get("risk_evaluator")
    if not evaluator or not isinstance(evaluator, RiskEvaluator):
        evaluator = RiskEvaluator(rule_gate=RuleGate())

    result = await evaluator.evaluate(tool_name, args, tool_risk)

    if result.decision == GateResult.DENIED:
        return {"error": f"Blocked: {result.reasoning}"}

    if result.decision == GateResult.NEEDS_APPROVAL:
        approved = approval_bridge.request_approval(tool_name, args, result.risk_score.level)
        if not approved:
            return {"error": f"User declined to approve '{tool_name}'."}

    # GateResult.ALLOWED — proceed
    return None
