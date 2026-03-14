"""Tests for RuleGate — Layer 1: Fast static risk evaluation."""

import pytest
from agent_risk_engine.models import THRESHOLD_ALIASES, GateResult
from agent_risk_engine.rule_gate import RuleGate

# --- Threshold resolution ---


class TestThresholdResolution:
    def test_integer(self):
        assert RuleGate(threshold=3).threshold == 3

    @pytest.mark.parametrize("alias, expected", list(THRESHOLD_ALIASES.items()))
    def test_aliases(self, alias, expected):
        assert RuleGate(threshold=alias).threshold == expected

    def test_numeric_string(self):
        assert RuleGate(threshold="4").threshold == 4

    def test_invalid_string(self):
        with pytest.raises(ValueError):
            RuleGate(threshold="invalid")


# --- Defaults ---


class TestDefaults:
    def test_default_threshold(self):
        assert RuleGate().threshold == 2

    def test_default_strict(self):
        assert RuleGate().strict is False

    def test_default_override_sets(self):
        gate = RuleGate()
        assert gate.allowed_tools == set()
        assert gate.approve_tools == set()
        assert gate.denied_tools == set()


# --- Evaluation order: denied → allowed → approve → threshold ---


class TestEvaluationOrder:
    def test_denied_always_denied(self):
        gate = RuleGate(threshold=5, denied_tools={"tool"})
        assert gate.evaluate("tool", tool_risk=1) == GateResult.DENIED

    def test_denied_overrides_allowed(self):
        gate = RuleGate(denied_tools={"tool"}, allowed_tools={"tool"})
        assert gate.evaluate("tool", tool_risk=1) == GateResult.DENIED

    def test_denied_overrides_approve(self):
        gate = RuleGate(denied_tools={"tool"}, approve_tools={"tool"})
        assert gate.evaluate("tool", tool_risk=1) == GateResult.DENIED

    def test_allowed_always_allowed(self):
        gate = RuleGate(threshold=1, allowed_tools={"tool"})
        assert gate.evaluate("tool", tool_risk=5) == GateResult.ALLOWED

    def test_allowed_overrides_approve(self):
        gate = RuleGate(allowed_tools={"tool"}, approve_tools={"tool"})
        assert gate.evaluate("tool", tool_risk=5) == GateResult.ALLOWED

    def test_approve_always_needs_approval(self):
        gate = RuleGate(threshold=5, approve_tools={"tool"})
        assert gate.evaluate("tool", tool_risk=1) == GateResult.NEEDS_APPROVAL

    def test_tool_in_all_three_sets(self):
        gate = RuleGate(
            denied_tools={"tool"},
            allowed_tools={"tool"},
            approve_tools={"tool"},
        )
        assert gate.evaluate("tool", tool_risk=1) == GateResult.DENIED


# --- Threshold boundary ---


class TestThresholdBoundary:
    def test_at_threshold(self):
        gate = RuleGate(threshold=3)
        assert gate.evaluate("tool", tool_risk=3) == GateResult.ALLOWED

    def test_below_threshold(self):
        gate = RuleGate(threshold=3)
        assert gate.evaluate("tool", tool_risk=1) == GateResult.ALLOWED

    def test_above_threshold_non_strict(self):
        gate = RuleGate(threshold=2, strict=False)
        assert gate.evaluate("tool", tool_risk=3) == GateResult.NEEDS_APPROVAL

    def test_above_threshold_strict(self):
        gate = RuleGate(threshold=2, strict=True)
        assert gate.evaluate("tool", tool_risk=3) == GateResult.DENIED


# --- Parameterized threshold sweep (5x5 matrix) ---


@pytest.mark.parametrize("threshold", range(1, 6))
@pytest.mark.parametrize("tool_risk", range(1, 6))
class TestThresholdSweep:
    def test_non_strict(self, threshold, tool_risk):
        gate = RuleGate(threshold=threshold, strict=False)
        result = gate.evaluate("tool", tool_risk=tool_risk)
        if tool_risk <= threshold:
            assert result == GateResult.ALLOWED
        else:
            assert result == GateResult.NEEDS_APPROVAL

    def test_strict(self, threshold, tool_risk):
        gate = RuleGate(threshold=threshold, strict=True)
        result = gate.evaluate("tool", tool_risk=tool_risk)
        if tool_risk <= threshold:
            assert result == GateResult.ALLOWED
        else:
            assert result == GateResult.DENIED


# --- Label ---


class TestLabel:
    @pytest.mark.parametrize("alias, level", list(THRESHOLD_ALIASES.items()))
    def test_known_alias(self, alias, level):
        assert RuleGate(threshold=level).label == alias

    def test_custom_level(self):
        assert RuleGate(threshold=4).label == "custom (level 4)"
