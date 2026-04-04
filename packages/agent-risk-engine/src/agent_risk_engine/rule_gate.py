"""RuleGate — Layer 1: Fast static risk evaluation.

No LLM calls. Evaluates action risk against a threshold with per-name
overrides and per-kind threshold routing.
Framework-agnostic — no external dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import THRESHOLD_ALIASES, GateResult

if TYPE_CHECKING:
    from .models import Action


class RuleGate:
    """Fast heuristic gate using threshold comparison and per-action overrides.

    Args:
        threshold: Risk levels at or below this are auto-allowed (1-5).
            Also accepts string aliases: "read-only", "cautious", "standard", "full-trust".
        strict: When True, actions above threshold are denied outright.
            When False, they require approval.
        allowed: Action names that are always auto-allowed regardless of threshold.
        approve: Action names that always require approval even if threshold would allow.
        denied: Action names that are always denied.
        kind_thresholds: Per-kind threshold overrides. Keys are action kinds,
            values are thresholds (int or alias). Actions whose kind matches
            use this threshold instead of the default.
    """

    def __init__(
        self,
        threshold: int | str = 2,
        strict: bool = False,
        allowed: set[str] | None = None,
        approve: set[str] | None = None,
        denied: set[str] | None = None,
        kind_thresholds: dict[str, int | str] | None = None,
    ) -> None:
        self.threshold = self._resolve_threshold(threshold)
        self.strict = strict
        self.allowed = allowed or set()
        self.approve = approve or set()
        self.denied = denied or set()
        self._kind_thresholds: dict[str, int] = {
            k: self._resolve_threshold(v) for k, v in (kind_thresholds or {}).items()
        }

    @staticmethod
    def _resolve_threshold(value: int | str) -> int:
        """Resolve a threshold value, accepting integers or named aliases."""
        if isinstance(value, str):
            if value in THRESHOLD_ALIASES:
                return THRESHOLD_ALIASES[value]
            return int(value)
        return value

    def evaluate(self, action: Action) -> GateResult:
        """Evaluate whether an action should be allowed, need approval, or be denied.

        Args:
            action: The Action to evaluate.

        Returns:
            GateResult indicating the decision.
        """
        if action.name in self.denied:
            return GateResult.DENIED
        if action.name in self.allowed:
            return GateResult.ALLOWED
        if action.name in self.approve:
            return GateResult.NEEDS_APPROVAL

        effective_threshold = self._kind_thresholds.get(action.kind, self.threshold)
        if action.risk <= effective_threshold:
            return GateResult.ALLOWED
        return GateResult.DENIED if self.strict else GateResult.NEEDS_APPROVAL

    @property
    def label(self) -> str:
        """Human-readable label for the current threshold."""
        for name, val in THRESHOLD_ALIASES.items():
            if val == self.threshold:
                return name
        return f"custom (level {self.threshold})"
