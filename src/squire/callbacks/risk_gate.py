"""Risk gate callback factory — creates ADK before_tool_callbacks for the risk pipeline.

Produces callbacks that translate between the framework-agnostic RiskEvaluator
and ADK's callback signature. Supports both interactive (with ApprovalProvider)
and headless (auto-deny + optional notification) modes.
"""

import logging
from typing import Any

from agent_risk_engine import Action, GateResult, PatternAnalyzer, RiskEvaluator, RiskPattern, RuleGate
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from ..approval import ApprovalProvider, AsyncApprovalProvider
from ..tools import TOOL_RISK_LEVELS
from ..types import BeforeToolCallback
from ..watch_autonomy import action_signature

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

# Homelab-specific risk patterns that supplement agent-risk-engine defaults.
HOMELAB_PATTERNS: list[RiskPattern] = [
    RiskPattern(r"--privileged", 5, "Privileged container mode"),
    RiskPattern(r"\biptables\b|\bufw\b|\bnftables\b", 4, "Firewall rule modification"),
    RiskPattern(r"\bsystemctl\s+(mask|disable)\b", 4, "Service disablement"),
    RiskPattern(r"/var/lib/docker/", 4, "Docker data directory access"),
    RiskPattern(r"/etc/docker/", 4, "Docker daemon configuration"),
    RiskPattern(r"\bssh-keygen\b|\bauthorized_keys\b", 4, "SSH key modification"),
    RiskPattern(r"\bcrontab\s+-[re]", 3, "Crontab modification"),
]

_SHARED_PATTERN_ANALYZER = PatternAnalyzer(extra_patterns=HOMELAB_PATTERNS)


def build_pattern_analyzer() -> PatternAnalyzer:
    """Return the shared PatternAnalyzer with default + homelab-specific patterns."""
    return _SHARED_PATTERN_ANALYZER


def is_adk_internal_tool(tool_name: str | None) -> bool:
    """Return True when the tool is an ADK-injected framework primitive."""
    if not tool_name:
        return False
    return tool_name in _ADK_INTERNAL_TOOLS


def _set_from_state(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, set):
        return {str(v) for v in value}
    if isinstance(value, (list, tuple)):
        return {str(v) for v in value}
    return set()


def _build_evaluator_from_state(tool_context: ToolContext, *, default_threshold: int | None) -> RiskEvaluator:
    """Build a fresh evaluator from serializable session-state values."""
    state = tool_context.state
    threshold_input = default_threshold if default_threshold is not None else state.get("risk_tolerance", 3)
    threshold = RuleGate(threshold=threshold_input).threshold
    strict = bool(state.get("risk_strict", False))
    allowed = _set_from_state(state.get("risk_allowed_tools"))
    approve = _set_from_state(state.get("risk_approval_tools"))
    denied = _set_from_state(state.get("risk_denied_tools"))
    return RiskEvaluator(
        rule_gate=RuleGate(
            threshold=threshold,
            strict=strict,
            allowed=allowed,
            approve=approve,
            denied=denied,
        ),
        analyzer=build_pattern_analyzer(),
    )


def create_risk_gate(
    tool_risk_levels: dict[str, int] | None = None,
    risk_overrides: dict[str, int] | None = None,
    approval_provider: ApprovalProvider | None = None,
    default_threshold: int | None = None,
    headless: bool = False,
    notifier: Any | None = None,
) -> BeforeToolCallback:
    """Create a before_tool_callback for the risk evaluation pipeline.

    Args:
        tool_risk_levels: Tool-to-risk-level mapping for this scope.
            Defaults to the global TOOL_RISK_LEVELS if not provided.
        risk_overrides: Per-tool risk level overrides from guardrails config.
            Keys are tool names or tool:action compound names.
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
    _overrides = risk_overrides or {}

    async def _risk_gate_callback(
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict | None:
        tool_name = tool.name

        # Allow ADK framework tools that are auto-injected (e.g., agent transfer)
        if is_adk_internal_tool(tool_name):
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

        # Disabling a multi-action tool (e.g. `docker_container`) must block every
        # action on that tool. The RuleGate denied set only matches the Action.name
        # we pass in (compound), so check the bare tool name ourselves.
        denied_tools = _set_from_state(tool_context.state.get("risk_denied_tools"))
        if tool_name in denied_tools:
            return {
                "error": (
                    f"[BLOCKED] '{compound_name}' was denied by the risk policy: "
                    f"tool '{tool_name}' is disabled. "
                    "Do NOT retry this tool call. Tell the user it was blocked and suggest alternatives."
                )
            }

        tool_risk = scoped_risk_levels[compound_name]

        # Apply per-tool risk override if configured
        if compound_name in _overrides:
            tool_risk = _overrides[compound_name]
        elif tool_name in _overrides:
            tool_risk = _overrides[tool_name]

        # Bump risk for remote host operations
        host = args.get("host", "local")
        if host != "local":
            tool_risk = min(tool_risk + 1, 5)

        # Watch-mode action cooldown blocks repeated/flapping signatures.
        blocked_signatures = set(tool_context.state.get("watch_blocked_action_signatures") or [])
        signature = action_signature(tool_name, args)
        if signature in blocked_signatures:
            return {
                "error": (
                    f"[BLOCKED] '{compound_name}' suppressed by watch cooldown policy to prevent flapping. "
                    "Do NOT retry this action in this cycle."
                )
            }

        # Bump risk for forced operations
        if args.get("force"):
            tool_risk = min(tool_risk + 1, 5)

        evaluator = _build_evaluator_from_state(tool_context, default_threshold=default_threshold)

        action = Action(kind="tool_call", name=compound_name, parameters=args, risk=tool_risk)
        result = await evaluator.evaluate(action)

        risk_threshold = evaluator.rule_gate.threshold
        analyzer_escalated = result.decision == GateResult.ALLOWED and result.risk_score.level > risk_threshold

        if result.decision == GateResult.DENIED:
            if headless and notifier:
                await _notify_blocked(notifier, compound_name, args, result.reasoning)
            return {
                "error": (
                    f"[BLOCKED] '{compound_name}' was denied by the risk policy: {result.reasoning}. "
                    "Do NOT retry this tool call. Tell the user it was blocked and suggest alternatives."
                )
            }

        if result.decision == GateResult.NEEDS_APPROVAL or analyzer_escalated:
            if headless:
                if notifier:
                    await _notify_blocked(notifier, compound_name, args, result.reasoning)
                return {
                    "error": (
                        f"[BLOCKED] '{compound_name}' denied in watch mode: above risk threshold. "
                        "Do NOT retry. Note this in your response and move on."
                    )
                }

            if approval_provider is not None:
                if isinstance(approval_provider, AsyncApprovalProvider):
                    approved = await approval_provider.request_approval_async(
                        compound_name, args, result.risk_score.level
                    )
                else:
                    approved = approval_provider.request_approval(compound_name, args, result.risk_score.level)
                if not approved:
                    return {
                        "error": (
                            f"[DENIED] The user declined '{compound_name}'. "
                            "Do NOT retry. Acknowledge the denial and move on."
                        )
                    }
            else:
                return {
                    "error": (
                        f"[BLOCKED] '{compound_name}' requires approval but no approval provider is available. "
                        "Do NOT retry. Inform the user."
                    )
                }

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
