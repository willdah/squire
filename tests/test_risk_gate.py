"""Tests for the layered risk evaluation system."""

import pytest

from agent_risk_engine import (
    GateResult,
    PassthroughActionGate,
    PassthroughAnalyzer,
    NullStateMonitor,
    RiskEvaluator,
    RiskLevel,
    RuleGate,
)


class TestRuleGate:
    """Tests for Layer 1: RuleGate static evaluation."""

    def test_threshold_allows_at_or_below(self):
        gate = RuleGate(threshold=2)
        assert gate.evaluate("system_info", 1) == GateResult.ALLOWED
        assert gate.evaluate("docker_logs", 2) == GateResult.ALLOWED

    def test_threshold_requires_approval_above(self):
        gate = RuleGate(threshold=2, strict=False)
        assert gate.evaluate("docker_compose", 3) == GateResult.NEEDS_APPROVAL
        assert gate.evaluate("run_command", 5) == GateResult.NEEDS_APPROVAL

    def test_strict_denies_above_threshold(self):
        gate = RuleGate(threshold=2, strict=True)
        assert gate.evaluate("docker_compose", 3) == GateResult.DENIED
        assert gate.evaluate("run_command", 5) == GateResult.DENIED

    def test_strict_still_allows_at_or_below(self):
        gate = RuleGate(threshold=2, strict=True)
        assert gate.evaluate("system_info", 1) == GateResult.ALLOWED
        assert gate.evaluate("docker_logs", 2) == GateResult.ALLOWED

    def test_threshold_5_allows_everything(self):
        gate = RuleGate(threshold=5)
        for level in range(1, 6):
            assert gate.evaluate("any_tool", level) == GateResult.ALLOWED

    def test_threshold_1_strict_denies_2_plus(self):
        gate = RuleGate(threshold=1, strict=True)
        assert gate.evaluate("system_info", 1) == GateResult.ALLOWED
        assert gate.evaluate("docker_logs", 2) == GateResult.DENIED

    def test_denied_tool_override(self):
        gate = RuleGate(threshold=5, denied_tools={"run_command"})
        assert gate.evaluate("run_command", 5) == GateResult.DENIED

    def test_allowed_tool_override(self):
        gate = RuleGate(threshold=1, allowed_tools={"run_command"})
        assert gate.evaluate("run_command", 5) == GateResult.ALLOWED

    def test_approve_tool_override(self):
        gate = RuleGate(threshold=5, approve_tools={"system_info"})
        assert gate.evaluate("system_info", 1) == GateResult.NEEDS_APPROVAL

    def test_deny_takes_precedence_over_allow(self):
        gate = RuleGate(threshold=5, allowed_tools={"tool"}, denied_tools={"tool"})
        assert gate.evaluate("tool", 1) == GateResult.DENIED


class TestAliasResolution:
    """Tests for threshold alias resolution."""

    def test_cautious_alias(self):
        gate = RuleGate(threshold="cautious")
        assert gate.threshold == 2

    def test_read_only_alias(self):
        gate = RuleGate(threshold="read-only")
        assert gate.threshold == 1

    def test_standard_alias(self):
        gate = RuleGate(threshold="standard")
        assert gate.threshold == 3

    def test_full_trust_alias(self):
        gate = RuleGate(threshold="full-trust")
        assert gate.threshold == 5

    def test_numeric_string(self):
        gate = RuleGate(threshold="3")
        assert gate.threshold == 3

    def test_integer_passthrough(self):
        gate = RuleGate(threshold=4)
        assert gate.threshold == 4

    def test_label_property(self):
        assert RuleGate(threshold=2).label == "cautious"
        assert RuleGate(threshold=4).label == "custom (level 4)"


class TestRiskLevel:
    """Tests for the RiskLevel IntEnum."""

    def test_ordering(self):
        assert RiskLevel.INFO < RiskLevel.LOW < RiskLevel.MODERATE < RiskLevel.HIGH < RiskLevel.CRITICAL

    def test_values(self):
        assert RiskLevel.INFO == 1
        assert RiskLevel.CRITICAL == 5

    def test_label(self):
        assert RiskLevel.MODERATE.label == "Moderate"


class TestRiskEvaluator:
    """Tests for the full pipeline with stub layers."""

    @pytest.mark.asyncio
    async def test_pipeline_allows_below_threshold(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3))
        result = await evaluator.evaluate("system_info", {}, 1)
        assert result.decision == GateResult.ALLOWED

    @pytest.mark.asyncio
    async def test_pipeline_needs_approval_above_threshold(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=2))
        result = await evaluator.evaluate("run_command", {"command": "ls"}, 5)
        assert result.decision == GateResult.NEEDS_APPROVAL

    @pytest.mark.asyncio
    async def test_pipeline_denies_strict(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=2, strict=True))
        result = await evaluator.evaluate("run_command", {"command": "ls"}, 5)
        assert result.decision == GateResult.DENIED

    @pytest.mark.asyncio
    async def test_pipeline_short_circuits_on_deny(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5, denied_tools={"bad_tool"}))
        result = await evaluator.evaluate("bad_tool", {}, 1)
        assert result.decision == GateResult.DENIED
        assert "denied" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_pipeline_returns_risk_score(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3))
        result = await evaluator.evaluate("docker_compose", {"action": "restart"}, 3)
        assert result.risk_score.level == 3

    @pytest.mark.asyncio
    async def test_pipeline_returns_system_state(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3))
        result = await evaluator.evaluate("system_info", {}, 1)
        assert result.system_state.healthy is True

    @pytest.mark.asyncio
    async def test_stubs_are_passthrough(self):
        """Stub layers should not alter the RuleGate's decision."""
        analyzer = PassthroughAnalyzer()
        monitor = NullStateMonitor()
        action_gate = PassthroughActionGate()

        score = await analyzer.analyze("test", {}, 3)
        assert score.level == 3

        state = monitor.check()
        assert state.healthy is True
        assert state.risk_adjustment == 0

        decision = action_gate.decide(GateResult.NEEDS_APPROVAL, score, state)
        assert decision == GateResult.NEEDS_APPROVAL
