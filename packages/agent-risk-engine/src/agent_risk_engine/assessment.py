"""RiskEvaluator — Orchestrates the layered risk evaluation pipeline.

Wires together RuleGate, ActionAnalyzer, and ActionGate into a single
stateless evaluation call. Returns a RiskResult with the decision and
all context needed by the consumer.
Framework-agnostic — no external dependencies.
"""

from __future__ import annotations

from .action_gate import ActionGate, PassthroughActionGate
from .analyzer import ActionAnalyzer, PassthroughAnalyzer
from .models import Action, GateResult, RiskLevel, RiskResult, RiskScore, UtilityScore
from .registry import ActionRegistry
from .rule_gate import RuleGate


class RiskEvaluator:
    """Orchestrates all risk evaluation layers into a single stateless pipeline.

    Args:
        rule_gate: Layer 1 — fast static rules (required).
        analyzer: Layer 2 — argument-aware risk analysis (optional, defaults to passthrough).
        action_gate: Layer 3 — final integration gate (optional, defaults to passthrough).
        registry: Optional action registry for metadata lookup.
        default_risk: Fallback risk level for unknown actions (1-5, default 5).
    """

    def __init__(
        self,
        rule_gate: RuleGate,
        analyzer: ActionAnalyzer | None = None,
        action_gate: ActionGate | None = None,
        registry: ActionRegistry | None = None,
        default_risk: int = 5,
    ) -> None:
        self.rule_gate = rule_gate
        self.analyzer: ActionAnalyzer = analyzer or PassthroughAnalyzer()
        self.action_gate: ActionGate = action_gate or PassthroughActionGate()
        self.registry = registry
        self.default_risk = default_risk

    async def evaluate(
        self,
        action: Action,
        utility: UtilityScore | None = None,
    ) -> RiskResult:
        """Run the full risk evaluation pipeline.

        Args:
            action: The Action to evaluate.
            utility: Optional caller-provided utility estimate.

        Returns:
            RiskResult with the final decision and all evaluation context.
        """
        # Layer 1: Fast static rules — short-circuit on hard deny
        rule_result = self.rule_gate.evaluate(action)
        if rule_result == GateResult.DENIED:
            level_label = RiskLevel(action.risk).label if 1 <= action.risk <= 5 else str(action.risk)
            return RiskResult(
                decision=GateResult.DENIED,
                risk_score=RiskScore(level=action.risk),
                reasoning=f"'{action.name}' is denied by rule gate (risk: {level_label} {action.risk}/5)",
            )

        # Layer 2: Analyze actual risk of this specific action
        risk_score = await self.analyzer.analyze(action)

        # Layer 3: Final decision
        final = self.action_gate.decide(rule_result, risk_score, utility)

        level_label = RiskLevel(risk_score.level).label if 1 <= risk_score.level <= 5 else str(risk_score.level)
        reasoning = risk_score.reasoning or (f"'{action.name}' evaluated at {level_label} ({risk_score.level}/5)")

        return RiskResult(
            decision=final,
            risk_score=risk_score,
            reasoning=reasoning,
            utility=utility,
        )
