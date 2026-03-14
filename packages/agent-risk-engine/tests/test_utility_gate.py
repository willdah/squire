"""Tests for RiskUtilityGate — Layer 4 risk-vs-utility escalation."""

import pytest
from agent_risk_engine.action_gate import RiskUtilityGate
from agent_risk_engine.models import GateResult, RiskScore, SystemState, UtilityScore


@pytest.fixture
def gate():
    return RiskUtilityGate()


# --- Passthrough when utility is None ---


class TestPassthroughWithoutUtility:
    @pytest.mark.parametrize("result", list(GateResult))
    def test_returns_rule_result_unchanged(self, gate, result):
        assert gate.decide(result, RiskScore(level=3), SystemState()) == result


# --- Hard deny always respected ---


class TestHardDeny:
    def test_denied_stays_denied_with_high_utility(self, gate):
        result = gate.decide(
            GateResult.DENIED,
            RiskScore(level=1),
            SystemState(),
            UtilityScore(level=5),
        )
        assert result == GateResult.DENIED

    def test_denied_stays_denied_with_zero_gap(self, gate):
        result = gate.decide(
            GateResult.DENIED,
            RiskScore(level=3),
            SystemState(),
            UtilityScore(level=3),
        )
        assert result == GateResult.DENIED


# --- No escalation when gap <= 0 ---


class TestNoEscalation:
    def test_equal_risk_and_utility(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=3),
            SystemState(),
            UtilityScore(level=3),
        )
        assert result == GateResult.ALLOWED

    def test_utility_exceeds_risk(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=2),
            SystemState(),
            UtilityScore(level=5),
        )
        assert result == GateResult.ALLOWED

    def test_needs_approval_not_relaxed(self, gate):
        """Utility > risk does NOT relax NEEDS_APPROVAL to ALLOWED."""
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=1),
            SystemState(),
            UtilityScore(level=5),
        )
        assert result == GateResult.NEEDS_APPROVAL


# --- Gap == 1: one step escalation ---


class TestGapOne:
    def test_allowed_to_needs_approval(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=3),
            SystemState(),
            UtilityScore(level=2),
        )
        assert result == GateResult.NEEDS_APPROVAL

    def test_needs_approval_to_denied(self, gate):
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=3),
            SystemState(),
            UtilityScore(level=2),
        )
        assert result == GateResult.DENIED


# --- Gap >= 2: two step escalation ---


class TestGapTwo:
    def test_allowed_to_denied(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=4),
            SystemState(),
            UtilityScore(level=2),
        )
        assert result == GateResult.DENIED

    def test_needs_approval_to_denied(self, gate):
        """Already at NEEDS_APPROVAL, 2 steps → clamped at DENIED."""
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=5),
            SystemState(),
            UtilityScore(level=1),
        )
        assert result == GateResult.DENIED

    def test_large_gap_clamps_at_denied(self, gate):
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=5),
            SystemState(),
            UtilityScore(level=1),
        )
        assert result == GateResult.DENIED


# --- Unhealthy system penalty ---


class TestUnhealthyPenalty:
    def test_gap_one_unhealthy_adds_step(self, gate):
        """gap=1 → 1 step, +1 for unhealthy = 2 steps total → ALLOWED→DENIED."""
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=3),
            SystemState(healthy=False),
            UtilityScore(level=2),
        )
        assert result == GateResult.DENIED

    def test_no_penalty_when_gap_zero(self, gate):
        """gap=0 → no escalation, unhealthy penalty only applies when gap > 0."""
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=3),
            SystemState(healthy=False),
            UtilityScore(level=3),
        )
        assert result == GateResult.ALLOWED

    def test_unhealthy_escalates_needs_approval(self, gate):
        """gap=1 + unhealthy → NEEDS_APPROVAL becomes DENIED."""
        result = gate.decide(
            GateResult.NEEDS_APPROVAL,
            RiskScore(level=2),
            SystemState(healthy=False),
            UtilityScore(level=1),
        )
        assert result == GateResult.DENIED


# --- risk_adjustment integration ---


class TestRiskAdjustment:
    def test_positive_adjustment_increases_effective_risk(self, gate):
        """risk=2, adjustment=+2 → effective=4, utility=3 → gap=1 → escalate."""
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=2),
            SystemState(risk_adjustment=2),
            UtilityScore(level=3),
        )
        assert result == GateResult.NEEDS_APPROVAL

    def test_negative_adjustment_decreases_effective_risk(self, gate):
        """risk=4, adjustment=-2 → effective=2, utility=3 → gap=-1 → no escalation."""
        result = gate.decide(
            GateResult.ALLOWED,
            RiskScore(level=4),
            SystemState(risk_adjustment=-2),
            UtilityScore(level=3),
        )
        assert result == GateResult.ALLOWED


# --- Parametric sweep ---


class TestParametricSweep:
    @pytest.mark.parametrize("risk", range(1, 6))
    @pytest.mark.parametrize("utility", range(1, 6))
    @pytest.mark.parametrize("healthy", [True, False])
    def test_never_relaxes(self, gate, risk, utility, healthy):
        """Gate should never return a less restrictive result than rule_result."""
        order = [GateResult.ALLOWED, GateResult.NEEDS_APPROVAL, GateResult.DENIED]
        for rule_result in order:
            result = gate.decide(
                rule_result,
                RiskScore(level=risk),
                SystemState(healthy=healthy),
                UtilityScore(level=utility),
            )
            assert order.index(result) >= order.index(rule_result), (
                f"Relaxed {rule_result}→{result} "
                f"(risk={risk}, utility={utility}, healthy={healthy})"
            )

    @pytest.mark.parametrize("risk", range(1, 6))
    @pytest.mark.parametrize("utility", range(1, 6))
    def test_healthy_no_escalation_when_utility_ge_risk(self, gate, risk, utility):
        """When utility >= risk in a healthy system, no escalation occurs."""
        if utility < risk:
            pytest.skip("Only testing utility >= risk")
        for rule_result in list(GateResult):
            result = gate.decide(
                rule_result,
                RiskScore(level=risk),
                SystemState(),
                UtilityScore(level=utility),
            )
            assert result == rule_result
