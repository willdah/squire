"""ActionGate — Layer 4: Final integration gate.

Protocol and implementations. RiskUtilityGate weighs risk against
caller-provided utility for a final go/no-go decision.
Framework-agnostic — no imports from squire or any agent framework.
"""

from __future__ import annotations

from typing import Protocol

from .models import GateResult, RiskScore, SystemState, UtilityScore

# Ordered from least to most restrictive for escalation arithmetic.
_ESCALATION_ORDER = [GateResult.ALLOWED, GateResult.NEEDS_APPROVAL, GateResult.DENIED]


class ActionGate(Protocol):
    """Final decision gate integrating all risk signals."""

    def decide(
        self,
        rule_result: GateResult,
        risk_score: RiskScore,
        system_state: SystemState,
        utility: UtilityScore | None = None,
    ) -> GateResult:
        """Make the final go/no-go decision.

        Args:
            rule_result: The RuleGate's initial decision.
            risk_score: The ToolAnalyzer's evaluated risk.
            system_state: Current system health from StateMonitor.
            utility: Optional caller-provided utility estimate.

        Returns:
            Final GateResult.
        """
        ...


class PassthroughActionGate:
    """Stub gate that defers to the RuleGate's decision."""

    def decide(
        self,
        rule_result: GateResult,
        risk_score: RiskScore,
        system_state: SystemState,
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
        system_state: SystemState,
        utility: UtilityScore | None = None,
    ) -> GateResult:
        # No utility provided → passthrough
        if utility is None:
            return rule_result

        # Layer 1 denials are sacred
        if rule_result == GateResult.DENIED:
            return GateResult.DENIED

        effective_risk = risk_score.level + system_state.risk_adjustment
        gap = effective_risk - utility.level

        if gap <= 0:
            # Utility justifies the risk — no escalation
            return rule_result

        # Determine escalation steps
        steps = min(gap, 2)  # gap==1 → 1 step, gap>=2 → 2 steps

        # Unhealthy system adds +1 escalation when gap > 0
        if not system_state.healthy:
            steps += 1

        idx = _ESCALATION_ORDER.index(rule_result)
        escalated_idx = min(idx + steps, len(_ESCALATION_ORDER) - 1)
        return _ESCALATION_ORDER[escalated_idx]
