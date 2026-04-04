"""Tests for RiskUtilityGate — Layer 3: risk vs utility final decision."""

import pytest
from agent_risk_engine import GateResult, RiskScore, RiskUtilityGate, UtilityScore


@pytest.fixture
def gate():
    return RiskUtilityGate()


class TestPassthroughWithoutUtility:
    @pytest.mark.parametrize("result", list(GateResult))
    def test_returns_rule_result_unchanged(self, gate, result):
        assert gate.decide(result, RiskScore(level=3)) == result


class TestHardDeny:
    def test_denied_stays_denied_with_high_utility(self, gate):
        result = gate.decide(
            GateResult.DENIED,
            RiskScore(level=1),
            utility=UtilityScore(level=5),
        )
        assert result == GateResult.DENIED

    def test_denied_stays_denied_with_zero_gap(self, gate):
        result = gate.decide(
            GateResult.DENIED,
            RiskScore(level=3),
            utility=UtilityScore(level=3),
        )
        assert result == GateResult.DENIED


class TestNoEscalation:
    def test_equal_risk_and_utility(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=3),
            utility=UtilityScore(level=3),
        )
        assert result == GateResult.ALLOWED

    def test_utility_exceeds_risk(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=2),
            utility=UtilityScore(level=4),
        )
        assert result == GateResult.ALLOWED

    def test_needs_approval_not_relaxed(self, gate):
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=2),
            utility=UtilityScore(level=5),
        )
        assert result == GateResult.NEEDS_APPROVAL


class TestGapOne:
    def test_allowed_to_needs_approval(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=3),
            utility=UtilityScore(level=2),
        )
        assert result == GateResult.NEEDS_APPROVAL

    def test_needs_approval_to_denied(self, gate):
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=3),
            utility=UtilityScore(level=2),
        )
        assert result == GateResult.DENIED


class TestGapTwo:
    def test_allowed_to_denied(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=4),
            utility=UtilityScore(level=2),
        )
        assert result == GateResult.DENIED

    def test_needs_approval_to_denied(self, gate):
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=5),
            utility=UtilityScore(level=2),
        )
        assert result == GateResult.DENIED

    def test_large_gap_clamps_at_denied(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=5),
            utility=UtilityScore(level=1),
        )
        assert result == GateResult.DENIED


class TestParametricSweep:
    @pytest.mark.parametrize("rule_result", list(GateResult))
    @pytest.mark.parametrize("risk", range(1, 6))
    @pytest.mark.parametrize("util", range(1, 6))
    def test_never_relaxes(self, gate, rule_result, risk, util):
        result = gate.decide(
            rule_result,
            RiskScore(level=risk),
            utility=UtilityScore(level=util),
        )
        order = [GateResult.ALLOWED, GateResult.NEEDS_APPROVAL, GateResult.DENIED]
        assert order.index(result) >= order.index(rule_result)

    @pytest.mark.parametrize("risk", range(1, 6))
    @pytest.mark.parametrize("util", range(1, 6))
    def test_no_escalation_when_utility_ge_risk(self, gate, risk, util):
        if util < risk:
            pytest.skip("Only testing utility >= risk")
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=risk),
            utility=UtilityScore(level=util),
        )
        assert result == GateResult.ALLOWED
