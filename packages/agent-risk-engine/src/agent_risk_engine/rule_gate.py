"""RuleGate — Layer 1: Fast static risk evaluation.

No LLM calls. Evaluates tool risk against a threshold with per-tool overrides.
Framework-agnostic — no imports from squire or any agent framework.
"""

from .models import GateResult, THRESHOLD_ALIASES


class RuleGate:
    """Fast heuristic gate using threshold comparison and per-tool overrides.

    Args:
        threshold: Risk levels at or below this are auto-allowed (1-5).
            Also accepts string aliases: "read-only", "cautious", "standard", "full-trust".
        strict: When True, tools above threshold are denied outright.
            When False, they require approval.
        allowed_tools: Tool names that are always auto-allowed regardless of threshold.
        approve_tools: Tool names that always require approval even if threshold would allow.
        denied_tools: Tool names that are always denied.
    """

    def __init__(
        self,
        threshold: int | str = 2,
        strict: bool = False,
        allowed_tools: set[str] | None = None,
        approve_tools: set[str] | None = None,
        denied_tools: set[str] | None = None,
    ) -> None:
        self.threshold = self._resolve_threshold(threshold)
        self.strict = strict
        self.allowed_tools = allowed_tools or set()
        self.approve_tools = approve_tools or set()
        self.denied_tools = denied_tools or set()

    @staticmethod
    def _resolve_threshold(value: int | str) -> int:
        """Resolve a threshold value, accepting integers or named aliases."""
        if isinstance(value, str):
            if value in THRESHOLD_ALIASES:
                return THRESHOLD_ALIASES[value]
            return int(value)
        return value

    def evaluate(self, tool_name: str, tool_risk: int) -> GateResult:
        """Evaluate whether a tool call should be allowed, need approval, or be denied.

        Args:
            tool_name: The name of the tool being invoked.
            tool_risk: The static risk level assigned to the tool (1-5).

        Returns:
            GateResult indicating the decision.
        """
        if tool_name in self.denied_tools:
            return GateResult.DENIED
        if tool_name in self.allowed_tools:
            return GateResult.ALLOWED
        if tool_name in self.approve_tools:
            return GateResult.NEEDS_APPROVAL
        if tool_risk <= self.threshold:
            return GateResult.ALLOWED
        return GateResult.DENIED if self.strict else GateResult.NEEDS_APPROVAL

    @property
    def label(self) -> str:
        """Human-readable label for the current threshold."""
        for name, val in THRESHOLD_ALIASES.items():
            if val == self.threshold:
                return name
        return f"custom (level {self.threshold})"
