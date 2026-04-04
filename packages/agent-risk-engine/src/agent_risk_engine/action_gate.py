"""ActionGate — Layer 3: Final integration gate.

Protocol and implementations. RiskUtilityGate weighs risk against
caller-provided utility for a final go/no-go decision.
Framework-agnostic — no external dependencies.
"""

from __future__ import annotations

from typing import Protocol

from .models import GateResult, RiskScore, UtilityScore

_ESCALATION_ORDER = [GateResult.ALLOWED, GateResult.NEEDS_APPROVAL, GateResult.DENIED]


class ActionGate(Protocol):
    """Final decision gate integrating all risk signals."""

    def decide(
        self,
        rule_result: GateResult,
        risk_score: RiskScore,
        utility: UtilityScore | None = None,
    ) -> GateResult:
        """Make the final go/no-go decision."""
        ...


class PassthroughActionGate:
    """Stub gate that defers to the RuleGate's decision."""

    def decide(
        self,
        rule_result: GateResult,
        risk_score: RiskScore,
        utility: UtilityScore | None = None,
    ) -> GateResult:
        return rule_result


class RiskUtilityGate:
    """Deterministic gate that escalates decisions when risk outweighs utility.

    Only escalates, never relaxes — cannot make a decision less restrictive
    than Layer 1's rule_result. Layer 1 DENIED results are always respected.
    """

    def decide(
        self,
        rule_result: GateResult,
        risk_score: RiskScore,
        utility: UtilityScore | None = None,
    ) -> GateResult:
        if utility is None:
            return rule_result

        if rule_result == GateResult.DENIED:
            return GateResult.DENIED

        gap = risk_score.level - utility.level

        if gap <= 0:
            return rule_result

        steps = min(gap, 2)

        idx = _ESCALATION_ORDER.index(rule_result)
        escalated_idx = min(idx + steps, len(_ESCALATION_ORDER) - 1)
        return _ESCALATION_ORDER[escalated_idx]
