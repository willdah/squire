"""Tests for passthrough/stub implementations."""
import pytest

from agent_risk_engine import (
    Action,
    GateResult,
    PassthroughActionGate,
    PassthroughAnalyzer,
    RiskScore,
    UtilityScore,
)


class TestPassthroughAnalyzer:
    @pytest.mark.parametrize("risk", range(1, 6))
    async def test_returns_same_level(self, risk):
        analyzer = PassthroughAnalyzer()
        result = await analyzer.analyze(Action(kind="tool_call", name="x", risk=risk))
        assert result.level == risk

    async def test_parameters_ignored(self):
        analyzer = PassthroughAnalyzer()
        result = await analyzer.analyze(
            Action(kind="tool_call", name="x", parameters={"key": "val"}, risk=3)
        )
        assert result.level == 3


class TestPassthroughActionGate:
    @pytest.mark.parametrize("result", list(GateResult))
    def test_returns_rule_result_unchanged(self, result):
        gate = PassthroughActionGate()
        assert gate.decide(result, RiskScore(level=5)) == result

    def test_ignores_risk(self):
        gate = PassthroughActionGate()
        assert gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=5),
        ) == GateResult.ALLOWED

    def test_accepts_and_ignores_utility(self):
        gate = PassthroughActionGate()
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=1),
            utility=UtilityScore(level=5),
        )
        assert result == GateResult.NEEDS_APPROVAL
