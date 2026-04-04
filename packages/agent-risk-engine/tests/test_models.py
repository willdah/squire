"""Tests for risk evaluation data models."""

import pytest
from agent_risk_engine import (
    THRESHOLD_ALIASES,
    Action,
    ActionDef,
    GateResult,
    RiskLevel,
    RiskResult,
    RiskScore,
    UtilityScore,
)


class TestRiskLevel:
    def test_values(self):
        assert RiskLevel.INFO == 1
        assert RiskLevel.LOW == 2
        assert RiskLevel.MODERATE == 3
        assert RiskLevel.HIGH == 4
        assert RiskLevel.CRITICAL == 5

    def test_ordering(self):
        assert RiskLevel.INFO < RiskLevel.LOW < RiskLevel.MODERATE < RiskLevel.HIGH < RiskLevel.CRITICAL

    @pytest.mark.parametrize(
        ("member", "expected"),
        [
            (RiskLevel.INFO, "Info"),
            (RiskLevel.LOW, "Low"),
            (RiskLevel.MODERATE, "Moderate"),
            (RiskLevel.HIGH, "High"),
            (RiskLevel.CRITICAL, "Critical"),
        ],
    )
    def test_label(self, member, expected):
        assert member.label == expected

    def test_usable_as_int(self):
        assert RiskLevel.MODERATE + 1 == 4


class TestGateResult:
    def test_members(self):
        assert GateResult.ALLOWED == "allowed"
        assert GateResult.NEEDS_APPROVAL == "needs_approval"
        assert GateResult.DENIED == "denied"

    def test_string_values(self):
        assert str(GateResult.ALLOWED) == "allowed"
        assert str(GateResult.DENIED) == "denied"


class TestThresholdAliases:
    def test_aliases(self):
        assert THRESHOLD_ALIASES == {
            "read-only": 1,
            "cautious": 2,
            "standard": 3,
            "full-trust": 5,
        }


class TestAction:
    def test_required_fields(self):
        action = Action(kind="tool_call", name="read_file")
        assert action.kind == "tool_call"
        assert action.name == "read_file"

    def test_defaults(self):
        action = Action(kind="tool_call", name="read_file")
        assert action.parameters == {}
        assert action.risk == 5
        assert action.metadata == {}

    def test_all_fields(self):
        action = Action(
            kind="file_write",
            name="write_config",
            parameters={"path": "/etc/config"},
            risk=4,
            metadata={"actor": "agent", "provenance": "autonomous"},
        )
        assert action.kind == "file_write"
        assert action.name == "write_config"
        assert action.parameters == {"path": "/etc/config"}
        assert action.risk == 4
        assert action.metadata == {"actor": "agent", "provenance": "autonomous"}

    def test_frozen(self):
        action = Action(kind="tool_call", name="read_file")
        with pytest.raises(AttributeError):
            action.name = "other"

    def test_equality(self):
        a = Action(kind="tool_call", name="read_file", risk=1)
        b = Action(kind="tool_call", name="read_file", risk=1)
        assert a == b

    def test_default_dicts_not_shared(self):
        a = Action(kind="tool_call", name="x")
        b = Action(kind="tool_call", name="y")
        assert a.parameters is not b.parameters
        assert a.metadata is not b.metadata


class TestActionDef:
    def test_required_fields(self):
        d = ActionDef(name="read_file", kind="tool_call", risk=1)
        assert d.name == "read_file"
        assert d.kind == "tool_call"
        assert d.risk == 1

    def test_defaults(self):
        d = ActionDef(name="read_file", kind="tool_call", risk=1)
        assert d.description == ""
        assert d.tags == frozenset()

    def test_with_tags(self):
        d = ActionDef(name="x", kind="tool_call", risk=2, tags=frozenset({"safe"}))
        assert "safe" in d.tags

    def test_frozen(self):
        d = ActionDef(name="x", kind="tool_call", risk=1)
        with pytest.raises(AttributeError):
            d.name = "other"


class TestRiskScore:
    def test_defaults(self):
        score = RiskScore(level=3)
        assert score.level == 3
        assert score.reasoning == ""

    def test_frozen(self):
        score = RiskScore(level=1)
        with pytest.raises(AttributeError):
            score.level = 2

    def test_equality(self):
        assert RiskScore(level=3) == RiskScore(level=3)

    def test_no_alternative_field(self):
        assert not hasattr(RiskScore(level=1), "alternative")


class TestRiskResult:
    def test_fields(self):
        result = RiskResult(
            decision=GateResult.ALLOWED,
            risk_score=RiskScore(level=1),
            reasoning="ok",
        )
        assert result.decision == GateResult.ALLOWED
        assert result.risk_score.level == 1
        assert result.reasoning == "ok"

    def test_no_system_state_field(self):
        result = RiskResult(decision=GateResult.ALLOWED, risk_score=RiskScore(level=1))
        assert not hasattr(result, "system_state")

    def test_utility_default_none(self):
        result = RiskResult(decision=GateResult.ALLOWED, risk_score=RiskScore(level=1))
        assert result.utility is None

    def test_utility_stored(self):
        u = UtilityScore(level=4, reasoning="needed")
        result = RiskResult(
            decision=GateResult.ALLOWED,
            risk_score=RiskScore(level=1),
            utility=u,
        )
        assert result.utility is u

    def test_frozen(self):
        result = RiskResult(decision=GateResult.ALLOWED, risk_score=RiskScore(level=1))
        with pytest.raises(AttributeError):
            result.decision = GateResult.DENIED


class TestUtilityScore:
    def test_defaults(self):
        u = UtilityScore(level=3)
        assert u.reasoning == ""

    def test_frozen(self):
        u = UtilityScore(level=3)
        with pytest.raises(AttributeError):
            u.level = 1

    def test_equality(self):
        assert UtilityScore(level=3) == UtilityScore(level=3)
