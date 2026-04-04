"""Risk gate callback factory — creates ADK before_tool_callbacks for the risk pipeline.

Produces callbacks that translate between the framework-agnostic RiskEvaluator
and ADK's callback signature. Supports both interactive (with ApprovalProvider)
and headless (auto-deny + optional notification) modes.
"""

import logging
from typing import Any

from agent_risk_engine import Action, GateResult, RiskEvaluator, RuleGate
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from ..approval import ApprovalProvider, AsyncApprovalProvider
from ..tools import TOOL_RISK_LEVELS
from ..types import BeforeToolCallback

logger = logging.getLogger(__name__)

# ADK framework tools that should bypass the risk gate and be hidden from users.
# These are auto-injected by ADK and are not user-facing tools.
ADK_INTERNAL_TOOLS = frozenset(
    {
        "transfer_to_agent",
    }
)

# Keep the private alias for backwards compatibility within this module.
_ADK_INTERNAL_TOOLS = ADK_INTERNAL_TOOLS


def create_risk_gate(
    tool_risk_levels: dict[str, int] | None = None,
    approval_provider: ApprovalProvider | None = None,
    default_threshold: int | None = None,
    headless: bool = False,
    notifier: Any | None = None,
) -> BeforeToolCallback:
    """Create a before_tool_callback for the risk evaluation pipeline.

    Args:
        tool_risk_levels: Tool-to-risk-level mapping for this scope.
            Defaults to the global TOOL_RISK_LEVELS if not provided.
        approval_provider: Provider for interactive approval requests.
            If None, NEEDS_APPROVAL results are auto-denied.
        default_threshold: Optional risk threshold override. When set,
            used instead of the session state's global threshold.
        headless: If True, NEEDS_APPROVAL is denied and a notification
            is dispatched via ``notifier`` (watch mode behavior).
        notifier: WebhookDispatcher instance for headless notifications.
            Only used when ``headless=True``.

    Returns:
        An async callback matching ADK's before_tool_callback signature.
    """
    scoped_risk_levels = tool_risk_levels or TOOL_RISK_LEVELS

    async def _risk_gate_callback(
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict | None:
        tool_name = tool.name

        # Allow ADK framework tools that are auto-injected (e.g., agent transfer)
        if tool_name in _ADK_INTERNAL_TOOLS:
            return None

        # Resolve compound action name: "tool:action" for tools with an action param
        action_param = args.get("action")
        if action_param:
            compound_name = f"{tool_name}:{action_param}"
        else:
            compound_name = tool_name

        # Unknown tools/actions (not in our scope and not ADK internal) are denied.
        # Fallback: if compound name not found, try the bare tool name (for tools
        # that use a single RISK_LEVEL rather than per-action RISK_LEVELS).
        if compound_name not in scoped_risk_levels:
            if action_param and tool_name in scoped_risk_levels:
                compound_name = tool_name
            else:
                return {"error": f"Blocked: unknown tool '{compound_name}'."}

        tool_risk = scoped_risk_levels[compound_name]

        # Bump risk for remote host operations
        host = args.get("host", "local")
        if host != "local":
            tool_risk = min(tool_risk + 1, 5)

        # Bump risk for forced operations
        if args.get("force"):
            tool_risk = min(tool_risk + 1, 5)

        # Load the risk evaluator from session state
        evaluator = tool_context.state.get("risk_evaluator")
        if not evaluator or not isinstance(evaluator, RiskEvaluator):
            evaluator = RiskEvaluator(rule_gate=RuleGate())

        action = Action(kind="tool_call", name=compound_name, parameters=args, risk=tool_risk)
        result = await evaluator.evaluate(action)

        if result.decision == GateResult.DENIED:
            if headless and notifier:
                await _notify_blocked(notifier, compound_name, args, result.reasoning)
            return {"error": f"Blocked: {result.reasoning}"}

        if result.decision == GateResult.NEEDS_APPROVAL:
            if headless:
                if notifier:
                    await _notify_blocked(notifier, compound_name, args, result.reasoning)
                return {"error": f"Watch mode denied '{compound_name}': above risk threshold."}

            if approval_provider is not None:
                if isinstance(approval_provider, AsyncApprovalProvider):
                    approved = await approval_provider.request_approval_async(
                        compound_name, args, result.risk_score.level
                    )
                else:
                    approved = approval_provider.request_approval(compound_name, args, result.risk_score.level)
                if not approved:
                    return {"error": f"User declined to approve '{compound_name}'."}
            else:
                return {"error": f"No approval provider — auto-denied '{compound_name}'."}

        # GateResult.ALLOWED — proceed
        return None

    return _risk_gate_callback


async def _notify_blocked(notifier: Any, action_name: str, args: dict, reasoning: str) -> None:
    """Dispatch a watch.blocked notification for a denied tool call."""
    try:
        await notifier.dispatch(
            category="watch.blocked",
            summary=f"Denied tool '{action_name}': {reasoning}",
            tool_name=action_name,
            details=str(args),
        )
    except Exception:
        logger.debug("Failed to dispatch watch.blocked notification", exc_info=True)
