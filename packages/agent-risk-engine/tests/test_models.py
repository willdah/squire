"""Tests for core data models."""

import pytest
from agent_risk_engine.models import (
    THRESHOLD_ALIASES,
    GateResult,
    RiskLevel,
    RiskResult,
    RiskScore,
    SystemState,
    UtilityScore,
)

# --- RiskLevel ---


class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.INFO == 1
        assert RiskLevel.LOW == 2
        assert RiskLevel.MODERATE == 3
        assert RiskLevel.HIGH == 4
        assert RiskLevel.CRITICAL == 5

    def test_ordering(self):
        assert RiskLevel.INFO < RiskLevel.CRITICAL
        assert RiskLevel.LOW <= RiskLevel.MODERATE
        assert RiskLevel.HIGH > RiskLevel.LOW

    @pytest.mark.parametrize(
        "level, expected",
        [
            (RiskLevel.INFO, "Info"),
            (RiskLevel.LOW, "Low"),
            (RiskLevel.MODERATE, "Moderate"),
            (RiskLevel.HIGH, "High"),
            (RiskLevel.CRITICAL, "Critical"),
        ],
    )
    def test_label(self, level, expected):
        assert level.label == expected

    def test_usable_as_int(self):
        assert RiskLevel.LOW <= 2
        assert RiskLevel.CRITICAL + 0 == 5


# --- GateResult ---


class TestGateResult:
    def test_members(self):
        assert set(GateResult) == {
            GateResult.ALLOWED,
            GateResult.NEEDS_APPROVAL,
            GateResult.DENIED,
        }

    def test_string_values(self):
        assert GateResult.ALLOWED == "allowed"
        assert GateResult.NEEDS_APPROVAL == "needs_approval"
        assert GateResult.DENIED == "denied"


# --- THRESHOLD_ALIASES ---


class TestThresholdAliases:
    def test_aliases(self):
        assert THRESHOLD_ALIASES == {
            "read-only": 1,
            "cautious": 2,
            "standard": 3,
            "full-trust": 5,
        }


# --- RiskScore ---


class TestRiskScore:
    def test_defaults(self):
        score = RiskScore(level=3)
        assert score.level == 3
        assert score.reasoning == ""
        assert score.alternative == ""

    def test_frozen(self):
        score = RiskScore(level=3)
        with pytest.raises(AttributeError):
            score.level = 4  # type: ignore[misc]

    def test_equality(self):
        assert RiskScore(level=3, reasoning="x") == RiskScore(level=3, reasoning="x")
        assert RiskScore(level=3) != RiskScore(level=4)


# --- SystemState ---


class TestSystemState:
    def test_defaults(self):
        state = SystemState()
        assert state.healthy is True
        assert state.warnings == []
        assert state.risk_adjustment == 0

    def test_frozen(self):
        state = SystemState()
        with pytest.raises(AttributeError):
            state.healthy = False  # type: ignore[misc]

    def test_warnings_not_shared(self):
        a = SystemState()
        b = SystemState()
        assert a.warnings is not b.warnings


# --- RiskResult ---


class TestRiskResult:
    def test_fields(self):
        result = RiskResult(
            decision=GateResult.ALLOWED,
            risk_score=RiskScore(level=1),
            system_state=SystemState(),
        )
        assert result.decision == GateResult.ALLOWED
        assert result.reasoning == ""

    def test_utility_default_none(self):
        result = RiskResult(
            decision=GateResult.ALLOWED,
            risk_score=RiskScore(level=1),
            system_state=SystemState(),
        )
        assert result.utility is None

    def test_utility_stored(self):
        u = UtilityScore(level=4, reasoning="helpful")
        result = RiskResult(
            decision=GateResult.ALLOWED,
            risk_score=RiskScore(level=1),
            system_state=SystemState(),
            utility=u,
        )
        assert result.utility == u

    def test_frozen(self):
        result = RiskResult(
            decision=GateResult.ALLOWED,
            risk_score=RiskScore(level=1),
            system_state=SystemState(),
        )
        with pytest.raises(AttributeError):
            result.decision = GateResult.DENIED  # type: ignore[misc]


# --- UtilityScore ---


class TestUtilityScore:
    def test_defaults(self):
        u = UtilityScore(level=3)
        assert u.level == 3
        assert u.reasoning == ""

    def test_frozen(self):
        u = UtilityScore(level=3)
        with pytest.raises(AttributeError):
            u.level = 4  # type: ignore[misc]

    def test_equality(self):
        assert UtilityScore(level=3, reasoning="x") == UtilityScore(level=3, reasoning="x")
        assert UtilityScore(level=3) != UtilityScore(level=4)
