"""Tests for passthrough/stub implementations of Layers 2-4."""

import pytest
from agent_risk_engine.action_gate import PassthroughActionGate
from agent_risk_engine.analyzer import PassthroughAnalyzer
from agent_risk_engine.models import GateResult, RiskScore, SystemState, UtilityScore
from agent_risk_engine.state_monitor import NullStateMonitor

# --- PassthroughAnalyzer ---


class TestPassthroughAnalyzer:
    @pytest.mark.parametrize("risk", range(1, 6))
    async def test_returns_same_level(self, risk):
        score = await PassthroughAnalyzer().analyze("tool", {}, risk)
        assert score.level == risk
        assert score.reasoning == ""

    async def test_args_ignored(self):
        a = await PassthroughAnalyzer().analyze("tool", {"cmd": "rm -rf /"}, 3)
        b = await PassthroughAnalyzer().analyze("tool", {}, 3)
        assert a == b


# --- NullStateMonitor ---


class TestNullStateMonitor:
    def test_returns_healthy(self):
        state = NullStateMonitor().check()
        assert state == SystemState(healthy=True, warnings=[], risk_adjustment=0)

    def test_returns_equal_instances(self):
        monitor = NullStateMonitor()
        assert monitor.check() == monitor.check()


# --- PassthroughActionGate ---


class TestPassthroughActionGate:
    @pytest.mark.parametrize("decision", list(GateResult))
    def test_returns_rule_result_unchanged(self, decision):
        gate = PassthroughActionGate()
        result = gate.decide(decision, RiskScore(level=5), SystemState())
        assert result == decision

    def test_ignores_risk_and_state(self):
        gate = PassthroughActionGate()
        a = gate.decide(GateResult.ALLOWED, RiskScore(level=1), SystemState())
        b = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=5, reasoning="danger"),
            SystemState(healthy=False, risk_adjustment=3),
        )
        assert a == b

    def test_accepts_and_ignores_utility(self):
        gate = PassthroughActionGate()
        u = UtilityScore(level=5, reasoning="very useful")
        result = gate.decide(GateResult.ALLOWED, RiskScore(level=5), SystemState(), utility=u)
        assert result == GateResult.ALLOWED
