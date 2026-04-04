"""RiskEvaluator — Orchestrates the layered risk evaluation pipeline.

Wires together RuleGate, ActionAnalyzer, StateMonitor, and ActionGate
into a single evaluation call. Returns a RiskResult with the decision
and all context needed by the consumer.
Framework-agnostic — no imports from squire or any agent framework.
"""

from __future__ import annotations

from .action_gate import ActionGate, PassthroughActionGate
from .analyzer import ActionAnalyzer, PassthroughAnalyzer
from .models import GateResult, RiskLevel, RiskResult, RiskScore, SystemState, UtilityScore
from .registry import ToolRegistry
from .rule_gate import RuleGate
from .state_monitor import NullStateMonitor, StateMonitor


class RiskEvaluator:
    """Orchestrates all risk evaluation layers into a single pipeline.

    Args:
        rule_gate: Layer 1 — fast static rules (required).
        tool_analyzer: Layer 2 — argument-aware risk analysis (optional, defaults to passthrough).
        state_monitor: Layer 3 — system health context (optional, defaults to null).
        action_gate: Layer 4 — final integration gate (optional, defaults to passthrough).
        registry: Optional tool registry for automatic risk level lookup.
    """

    def __init__(
        self,
        rule_gate: RuleGate,
        tool_analyzer: ActionAnalyzer | None = None,
        state_monitor: StateMonitor | None = None,
        action_gate: ActionGate | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.rule_gate = rule_gate
        self.tool_analyzer: ActionAnalyzer = tool_analyzer or PassthroughAnalyzer()
        self.state_monitor: StateMonitor = state_monitor or NullStateMonitor()
        self.action_gate: ActionGate = action_gate or PassthroughActionGate()
        self.registry = registry

    async def evaluate(
        self,
        tool_name: str,
        args: dict,
        tool_risk: int | None = None,
        utility: UtilityScore | None = None,
    ) -> RiskResult:
        """Run the full risk evaluation pipeline.

        Args:
            tool_name: The name of the tool being invoked.
            args: The arguments being passed to the tool.
            tool_risk: The static risk level assigned to the tool (1-5).
                If None, looked up from the registry. Raises ValueError
                if neither tool_risk nor a registry is configured.

        Returns:
            RiskResult with the final decision and all evaluation context.
        """
        # Resolve tool_risk
        if tool_risk is None:
            if self.registry is None:
                raise ValueError("tool_risk must be provided when no registry is configured")
            tool_risk = self.registry.get_risk(tool_name)

        # Layer 1: Fast static rules — short-circuit on hard deny
        rule_result = self.rule_gate.evaluate(tool_name, tool_risk)
        if rule_result == GateResult.DENIED:
            level_label = RiskLevel(tool_risk).label if 1 <= tool_risk <= 5 else str(tool_risk)
            return RiskResult(
                decision=GateResult.DENIED,
                risk_score=RiskScore(level=tool_risk),
                system_state=SystemState(),
                reasoning=f"'{tool_name}' is denied by rule gate (risk: {level_label} {tool_risk}/5)",
            )

        # Layer 2: Analyze actual risk of this specific call
        risk_score = await self.tool_analyzer.analyze(tool_name, args, tool_risk)

        # Layer 3: Record call and check system state
        if hasattr(self.state_monitor, "record"):
            self.state_monitor.record(tool_name)
        system_state = self.state_monitor.check()

        # Layer 4: Final decision
        final = self.action_gate.decide(rule_result, risk_score, system_state, utility)

        level_label = RiskLevel(risk_score.level).label if 1 <= risk_score.level <= 5 else str(risk_score.level)
        reasoning = risk_score.reasoning or (f"'{tool_name}' evaluated at {level_label} ({risk_score.level}/5)")

        return RiskResult(
            decision=final,
            risk_score=risk_score,
            system_state=system_state,
            reasoning=reasoning,
            utility=utility,
        )
