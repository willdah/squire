"""Tests for RiskEvaluator — orchestrates the layered risk evaluation pipeline."""
import pytest

from agent_risk_engine import (
    Action,
    ActionRegistry,
    GateResult,
    PassthroughActionGate,
    PassthroughAnalyzer,
    RiskEvaluator,
    RiskLevel,
    RiskResult,
    RiskScore,
    RiskUtilityGate,
    RuleGate,
    UtilityScore,
)


class RecordingAnalyzer:
    def __init__(self, level: int = 3):
        self.calls: list[Action] = []
        self._level = level

    async def analyze(self, action: Action) -> RiskScore:
        self.calls.append(action)
        return RiskScore(level=self._level)


class RecordingActionGate:
    def __init__(self):
        self.calls: list[tuple] = []

    def decide(self, rule_result, risk_score, utility=None):
        self.calls.append((rule_result, risk_score, utility))
        return rule_result


class TestDefaultWiring:
    async def test_constructs_with_only_rule_gate(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate())
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=1))
        assert result.decision == GateResult.ALLOWED


class TestDeniedShortCircuit:
    async def test_denied_skips_layers_2_and_3(self):
        analyzer = RecordingAnalyzer()
        gate = RecordingActionGate()
        evaluator = RiskEvaluator(
            rule_gate=RuleGate(denied={"dangerous"}),
            analyzer=analyzer,
            action_gate=gate,
        )
        result = await evaluator.evaluate(Action(kind="tool_call", name="dangerous", risk=1))
        assert result.decision == GateResult.DENIED
        assert len(analyzer.calls) == 0
        assert len(gate.calls) == 0

    async def test_denied_result_has_static_risk(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(denied={"x"}))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3))
        assert result.risk_score.level == 3

    async def test_denied_reasoning_contains_action_name(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(denied={"my_action"}))
        result = await evaluator.evaluate(Action(kind="tool_call", name="my_action", risk=3))
        assert "my_action" in result.reasoning

    async def test_denied_reasoning_out_of_range_risk(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(denied={"x"}))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=10))
        assert "x" in result.reasoning


class TestFullPipeline:
    async def test_allowed_passes_all_layers(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3))
        assert result.decision == GateResult.ALLOWED

    async def test_needs_approval_passes_all_layers(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=2))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3))
        assert result.decision == GateResult.NEEDS_APPROVAL

    async def test_all_layers_invoked(self):
        analyzer = RecordingAnalyzer(level=3)
        gate = RecordingActionGate()
        evaluator = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            analyzer=analyzer,
            action_gate=gate,
        )
        action = Action(kind="tool_call", name="x", parameters={"key": "val"}, risk=3)
        await evaluator.evaluate(action)
        assert len(analyzer.calls) == 1
        assert analyzer.calls[0] is action
        assert len(gate.calls) == 1

    async def test_layer_3_receives_outputs_from_prior_layers(self):
        analyzer = RecordingAnalyzer(level=4)
        gate = RecordingActionGate()
        evaluator = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            analyzer=analyzer,
            action_gate=gate,
        )
        await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3))
        rule_result, risk_score, utility = gate.calls[0]
        assert rule_result == GateResult.ALLOWED
        assert risk_score.level == 4
        assert utility is None

    async def test_layer_3_can_override_layer_1(self):
        class EscalatingGate:
            def decide(self, rule_result, risk_score, utility=None):
                return GateResult.DENIED

        evaluator = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            action_gate=EscalatingGate(),
        )
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=1))
        assert result.decision == GateResult.DENIED


class TestReasoning:
    async def test_analyzer_reasoning_used_when_present(self):
        class ReasoningAnalyzer:
            async def analyze(self, action):
                return RiskScore(level=3, reasoning="Custom analysis result")

        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5), analyzer=ReasoningAnalyzer())
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3))
        assert result.reasoning == "Custom analysis result"

    async def test_default_reasoning_when_empty(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        result = await evaluator.evaluate(Action(kind="tool_call", name="test_tool", risk=2))
        assert "test_tool" in result.reasoning
        assert "Low" in result.reasoning

    async def test_default_reasoning_out_of_range_level(self):
        class HighAnalyzer:
            async def analyze(self, action):
                return RiskScore(level=7)

        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=10), analyzer=HighAnalyzer())
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=7))
        assert "7" in result.reasoning


class TestCustomLayers:
    async def test_custom_analyzer_receives_action(self):
        analyzer = RecordingAnalyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5), analyzer=analyzer)
        action = Action(kind="file_write", name="write_config", parameters={"path": "/etc/x"}, risk=4)
        await evaluator.evaluate(action)
        assert analyzer.calls[0] is action


class TestRegistryIntegration:
    async def test_risk_from_registry(self):
        registry = ActionRegistry()
        registry.register("read_file", "tool_call", 1)
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5), registry=registry)
        result = await evaluator.evaluate(Action(kind="tool_call", name="read_file", risk=1))
        assert result.decision == GateResult.ALLOWED

    async def test_default_risk_fallback(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=2), default_risk=3)
        result = await evaluator.evaluate(Action(kind="tool_call", name="unknown", risk=5))
        assert result.decision == GateResult.NEEDS_APPROVAL


class TestUtilityPassthrough:
    async def test_utility_passed_to_layer_3(self):
        gate = RecordingActionGate()
        evaluator = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            action_gate=gate,
        )
        utility = UtilityScore(level=4, reasoning="needed")
        await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3), utility=utility)
        assert gate.calls[0][2] is utility

    async def test_utility_in_result(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        utility = UtilityScore(level=4)
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3), utility=utility)
        assert result.utility is utility

    async def test_utility_none_when_not_provided(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=3))
        assert result.utility is None

    async def test_utility_none_in_denied_short_circuit(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(denied={"x"}))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=1))
        assert result.utility is None


class TestEndToEndRiskUtilityGate:
    async def test_utility_justifies_risk(self):
        evaluator = RiskEvaluator(
            rule_gate=RuleGate(threshold="standard"),
            action_gate=RiskUtilityGate(),
        )
        result = await evaluator.evaluate(
            Action(kind="tool_call", name="write_file", risk=3),
            utility=UtilityScore(level=4, reasoning="User requested"),
        )
        assert result.decision == GateResult.ALLOWED

    async def test_risk_outweighs_utility_escalates(self):
        evaluator = RiskEvaluator(
            rule_gate=RuleGate(threshold="standard"),
            action_gate=RiskUtilityGate(),
        )
        result = await evaluator.evaluate(
            Action(kind="tool_call", name="write_file", risk=3),
            utility=UtilityScore(level=1, reasoning="Speculative"),
        )
        assert result.decision == GateResult.DENIED


class TestNoSystemState:
    async def test_result_has_no_system_state(self):
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        result = await evaluator.evaluate(Action(kind="tool_call", name="x", risk=1))
        assert not hasattr(result, "system_state")
