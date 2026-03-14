"""Tests for RiskEvaluator — pipeline orchestration."""

import pytest
from agent_risk_engine.action_gate import PassthroughActionGate
from agent_risk_engine.analyzer import PassthroughAnalyzer
from agent_risk_engine.assessment import RiskEvaluator
from agent_risk_engine.models import GateResult, RiskScore, SystemState, UtilityScore
from agent_risk_engine.registry import ToolRegistry
from agent_risk_engine.rule_gate import RuleGate
from agent_risk_engine.state_monitor import CallTracker, NullStateMonitor

# --- Recording fakes for verifying layer interaction ---


class RecordingAnalyzer:
    """Records calls and returns a configurable RiskScore."""

    def __init__(self, score: RiskScore | None = None):
        self.calls: list[tuple[str, dict, int]] = []
        self._score = score

    async def analyze(self, tool_name: str, args: dict, tool_risk: int) -> RiskScore:
        self.calls.append((tool_name, args, tool_risk))
        return self._score or RiskScore(level=tool_risk)


class RecordingMonitor:
    """Records calls and returns a configurable SystemState."""

    def __init__(self, state: SystemState | None = None):
        self.call_count = 0
        self._state = state or SystemState()

    def check(self) -> SystemState:
        self.call_count += 1
        return self._state


class RecordingActionGate:
    """Records calls and returns a configurable GateResult."""

    def __init__(self, override: GateResult | None = None):
        self.calls: list[tuple[GateResult, RiskScore, SystemState, UtilityScore | None]] = []
        self._override = override

    def decide(
        self,
        rule_result: GateResult,
        risk_score: RiskScore,
        system_state: SystemState,
        utility: UtilityScore | None = None,
    ) -> GateResult:
        self.calls.append((rule_result, risk_score, system_state, utility))
        return self._override or rule_result


# --- Default wiring ---


class TestDefaultWiring:
    def test_constructs_with_only_rule_gate(self):
        ev = RiskEvaluator(rule_gate=RuleGate())
        assert isinstance(ev.tool_analyzer, PassthroughAnalyzer)
        assert isinstance(ev.state_monitor, NullStateMonitor)
        assert isinstance(ev.action_gate, PassthroughActionGate)


# --- Short-circuit on DENIED ---


class TestDeniedShortCircuit:
    async def test_denied_skips_layers_2_through_4(self):
        analyzer = RecordingAnalyzer()
        monitor = RecordingMonitor()
        action_gate = RecordingActionGate()

        ev = RiskEvaluator(
            rule_gate=RuleGate(denied_tools={"dangerous"}),
            tool_analyzer=analyzer,
            state_monitor=monitor,
            action_gate=action_gate,
        )
        result = await ev.evaluate("dangerous", {}, tool_risk=5)

        assert result.decision == GateResult.DENIED
        assert analyzer.calls == []
        assert monitor.call_count == 0
        assert action_gate.calls == []

    async def test_denied_result_has_static_risk(self):
        ev = RiskEvaluator(rule_gate=RuleGate(denied_tools={"tool"}))
        result = await ev.evaluate("tool", {}, tool_risk=3)
        assert result.risk_score.level == 3

    async def test_denied_result_has_default_system_state(self):
        ev = RiskEvaluator(rule_gate=RuleGate(denied_tools={"tool"}))
        result = await ev.evaluate("tool", {}, tool_risk=3)
        assert result.system_state == SystemState()

    async def test_denied_reasoning_contains_tool_name(self):
        ev = RiskEvaluator(rule_gate=RuleGate(denied_tools={"delete_db"}))
        result = await ev.evaluate("delete_db", {}, tool_risk=5)
        assert "delete_db" in result.reasoning
        assert "Critical" in result.reasoning

    async def test_denied_reasoning_out_of_range_risk(self):
        ev = RiskEvaluator(rule_gate=RuleGate(denied_tools={"tool"}))
        result = await ev.evaluate("tool", {}, tool_risk=7)
        assert "7" in result.reasoning


# --- Full pipeline ---


class TestFullPipeline:
    async def test_allowed_passes_all_layers(self):
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=3))
        result = await ev.evaluate("tool", {}, tool_risk=1)
        assert result.decision == GateResult.ALLOWED

    async def test_needs_approval_passes_all_layers(self):
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=2, strict=False))
        result = await ev.evaluate("tool", {}, tool_risk=4)
        assert result.decision == GateResult.NEEDS_APPROVAL

    async def test_all_layers_invoked(self):
        analyzer = RecordingAnalyzer()
        monitor = RecordingMonitor()
        action_gate = RecordingActionGate()

        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=3),
            tool_analyzer=analyzer,
            state_monitor=monitor,
            action_gate=action_gate,
        )
        await ev.evaluate("tool", {"key": "val"}, tool_risk=2)

        assert len(analyzer.calls) == 1
        assert analyzer.calls[0] == ("tool", {"key": "val"}, 2)
        assert monitor.call_count == 1
        assert len(action_gate.calls) == 1

    async def test_layer_4_receives_outputs_from_prior_layers(self):
        custom_score = RiskScore(level=4, reasoning="elevated")
        custom_state = SystemState(healthy=False, warnings=["loop"], risk_adjustment=1)

        analyzer = RecordingAnalyzer(score=custom_score)
        monitor = RecordingMonitor(state=custom_state)
        action_gate = RecordingActionGate()

        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            tool_analyzer=analyzer,
            state_monitor=monitor,
            action_gate=action_gate,
        )
        await ev.evaluate("tool", {}, tool_risk=2)

        rule_result, risk_score, system_state, utility = action_gate.calls[0]
        assert rule_result == GateResult.ALLOWED
        assert risk_score == custom_score
        assert system_state == custom_state
        assert utility is None

    async def test_layer_4_can_override_layer_1(self):
        action_gate = RecordingActionGate(override=GateResult.DENIED)

        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            tool_analyzer=RecordingAnalyzer(),
            state_monitor=RecordingMonitor(),
            action_gate=action_gate,
        )
        result = await ev.evaluate("tool", {}, tool_risk=1)
        assert result.decision == GateResult.DENIED


# --- Reasoning ---


class TestReasoning:
    async def test_analyzer_reasoning_used_when_present(self):
        analyzer = RecordingAnalyzer(score=RiskScore(level=3, reasoning="custom reason"))
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=5), tool_analyzer=analyzer)
        result = await ev.evaluate("tool", {}, tool_risk=3)
        assert result.reasoning == "custom reason"

    async def test_default_reasoning_when_empty(self):
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        result = await ev.evaluate("my_tool", {}, tool_risk=3)
        assert "my_tool" in result.reasoning
        assert "Moderate" in result.reasoning
        assert "3/5" in result.reasoning

    async def test_default_reasoning_out_of_range_level(self):
        analyzer = RecordingAnalyzer(score=RiskScore(level=10))
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=5), tool_analyzer=analyzer)
        result = await ev.evaluate("tool", {}, tool_risk=1)
        assert "10" in result.reasoning


# --- Custom layer injection ---


class TestCustomLayers:
    async def test_custom_analyzer_receives_args(self):
        analyzer = RecordingAnalyzer()
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=5), tool_analyzer=analyzer)
        await ev.evaluate("my_tool", {"x": 1}, tool_risk=4)

        assert analyzer.calls == [("my_tool", {"x": 1}, 4)]

    async def test_custom_state_in_result(self):
        custom_state = SystemState(healthy=False, warnings=["rate limit"])
        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            state_monitor=RecordingMonitor(state=custom_state),
        )
        result = await ev.evaluate("tool", {}, tool_risk=1)
        assert result.system_state == custom_state


# --- End-to-end integration ---


class TestEndToEnd:
    async def test_full_custom_pipeline(self):
        """All custom layers: analyzer escalates risk, monitor flags unhealthy,
        action gate denies based on system health."""

        class EscalatingAnalyzer:
            async def analyze(self, tool_name: str, args: dict, tool_risk: int) -> RiskScore:
                return RiskScore(level=min(tool_risk + 2, 5), reasoning="escalated")

        class UnhealthyMonitor:
            def check(self) -> SystemState:
                return SystemState(healthy=False, warnings=["overloaded"], risk_adjustment=2)

        class ConservativeGate:
            def decide(
                self,
                rule_result: GateResult,
                risk_score: RiskScore,
                system_state: SystemState,
                utility: UtilityScore | None = None,
            ) -> GateResult:
                if not system_state.healthy and risk_score.level >= 4:
                    return GateResult.DENIED
                return rule_result

        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            tool_analyzer=EscalatingAnalyzer(),
            state_monitor=UnhealthyMonitor(),
            action_gate=ConservativeGate(),
        )

        # tool_risk=3, escalated to 5 by analyzer, system unhealthy → DENIED
        result = await ev.evaluate("risky_tool", {}, tool_risk=3)
        assert result.decision == GateResult.DENIED
        assert result.risk_score.level == 5
        assert result.system_state.healthy is False
        assert result.reasoning == "escalated"


# --- Registry integration ---


class TestRegistryIntegration:
    async def test_risk_from_registry(self):
        reg = ToolRegistry()
        reg.register("read_file", 1)
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=3), registry=reg)

        result = await ev.evaluate("read_file", {})
        assert result.decision == GateResult.ALLOWED
        assert result.risk_score.level == 1

    async def test_unknown_tool_gets_default_risk(self):
        reg = ToolRegistry(default_risk=5)
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=2), registry=reg)

        result = await ev.evaluate("unknown_tool", {})
        assert result.decision == GateResult.NEEDS_APPROVAL
        assert result.risk_score.level == 5

    async def test_explicit_tool_risk_overrides_registry(self):
        reg = ToolRegistry()
        reg.register("tool", 1)
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=3), registry=reg)

        # Explicit tool_risk=5 should override registry's 1
        result = await ev.evaluate("tool", {}, tool_risk=5)
        assert result.risk_score.level == 5

    async def test_no_risk_no_registry_raises(self):
        ev = RiskEvaluator(rule_gate=RuleGate())
        with pytest.raises(ValueError, match="tool_risk"):
            await ev.evaluate("tool", {})


# --- CallTracker auto-recording ---


class TestCallTrackerAutoRecording:
    async def test_evaluator_records_to_call_tracker(self):
        tracker = CallTracker()
        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            state_monitor=tracker,
        )
        await ev.evaluate("tool_a", {}, tool_risk=1)
        await ev.evaluate("tool_b", {}, tool_risk=1)
        assert tracker.call_count == 2

    async def test_denied_does_not_record(self):
        tracker = CallTracker()
        ev = RiskEvaluator(
            rule_gate=RuleGate(denied_tools={"bad_tool"}),
            state_monitor=tracker,
        )
        await ev.evaluate("bad_tool", {}, tool_risk=5)
        assert tracker.call_count == 0

    async def test_loop_detection_through_evaluator(self):
        tracker = CallTracker(loop_threshold=3)
        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            state_monitor=tracker,
        )
        await ev.evaluate("stuck", {}, tool_risk=1)
        await ev.evaluate("stuck", {}, tool_risk=1)
        result = await ev.evaluate("stuck", {}, tool_risk=1)
        assert not result.system_state.healthy
        assert any("loop" in w.lower() for w in result.system_state.warnings)


# --- Utility pass-through ---


class TestUtilityPassthrough:
    async def test_utility_passed_to_layer_4(self):
        action_gate = RecordingActionGate()
        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            action_gate=action_gate,
        )
        u = UtilityScore(level=4, reasoning="helpful")
        await ev.evaluate("tool", {}, tool_risk=2, utility=u)

        _, _, _, recorded_utility = action_gate.calls[0]
        assert recorded_utility == u

    async def test_utility_in_result(self):
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        u = UtilityScore(level=3)
        result = await ev.evaluate("tool", {}, tool_risk=1, utility=u)
        assert result.utility == u

    async def test_utility_none_when_not_provided(self):
        ev = RiskEvaluator(rule_gate=RuleGate(threshold=5))
        result = await ev.evaluate("tool", {}, tool_risk=1)
        assert result.utility is None

    async def test_utility_none_in_denied_short_circuit(self):
        ev = RiskEvaluator(rule_gate=RuleGate(denied_tools={"tool"}))
        u = UtilityScore(level=5, reasoning="very useful")
        result = await ev.evaluate("tool", {}, tool_risk=3, utility=u)
        assert result.decision == GateResult.DENIED
        assert result.utility is None


# --- End-to-end with RiskUtilityGate ---


class TestEndToEndRiskUtilityGate:
    async def test_utility_justifies_risk(self):
        from agent_risk_engine.action_gate import RiskUtilityGate

        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            action_gate=RiskUtilityGate(),
        )
        result = await ev.evaluate("tool", {}, tool_risk=3, utility=UtilityScore(level=4))
        assert result.decision == GateResult.ALLOWED

    async def test_risk_outweighs_utility_escalates(self):
        from agent_risk_engine.action_gate import RiskUtilityGate

        ev = RiskEvaluator(
            rule_gate=RuleGate(threshold=5),
            action_gate=RiskUtilityGate(),
        )
        result = await ev.evaluate("tool", {}, tool_risk=4, utility=UtilityScore(level=2))
        assert result.decision == GateResult.DENIED
