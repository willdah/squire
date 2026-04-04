"""Tests for RuleGate — Layer 1: fast static risk evaluation."""
import pytest

from agent_risk_engine import Action, GateResult, RuleGate


class TestThresholdResolution:
    def test_integer(self):
        assert RuleGate(threshold=3).threshold == 3

    @pytest.mark.parametrize(("alias", "expected"), [("read-only", 1), ("cautious", 2), ("standard", 3), ("full-trust", 5)])
    def test_aliases(self, alias, expected):
        assert RuleGate(threshold=alias).threshold == expected

    def test_numeric_string(self):
        assert RuleGate(threshold="4").threshold == 4

    def test_invalid_string(self):
        with pytest.raises(ValueError):
            RuleGate(threshold="invalid")


class TestDefaults:
    def test_default_threshold(self):
        assert RuleGate().threshold == 2

    def test_default_strict(self):
        assert RuleGate().strict is False

    def test_default_override_sets(self):
        gate = RuleGate()
        assert gate.allowed == set()
        assert gate.approve == set()
        assert gate.denied == set()


class TestEvaluationOrder:
    def test_denied_always_denied(self):
        gate = RuleGate(denied={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=1)) == GateResult.DENIED

    def test_denied_overrides_allowed(self):
        gate = RuleGate(denied={"x"}, allowed={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=1)) == GateResult.DENIED

    def test_denied_overrides_approve(self):
        gate = RuleGate(denied={"x"}, approve={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=1)) == GateResult.DENIED

    def test_allowed_always_allowed(self):
        gate = RuleGate(threshold=1, allowed={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=5)) == GateResult.ALLOWED

    def test_allowed_overrides_approve(self):
        gate = RuleGate(allowed={"x"}, approve={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=5)) == GateResult.ALLOWED

    def test_approve_always_needs_approval(self):
        gate = RuleGate(threshold=5, approve={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=1)) == GateResult.NEEDS_APPROVAL

    def test_action_in_all_three_sets(self):
        gate = RuleGate(denied={"x"}, allowed={"x"}, approve={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=1)) == GateResult.DENIED


class TestThresholdBoundary:
    def test_at_threshold(self):
        gate = RuleGate(threshold=3)
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=3)) == GateResult.ALLOWED

    def test_below_threshold(self):
        gate = RuleGate(threshold=3)
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=1)) == GateResult.ALLOWED

    def test_above_threshold_non_strict(self):
        gate = RuleGate(threshold=3, strict=False)
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=4)) == GateResult.NEEDS_APPROVAL

    def test_above_threshold_strict(self):
        gate = RuleGate(threshold=3, strict=True)
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=4)) == GateResult.DENIED


class TestThresholdSweep:
    @pytest.mark.parametrize("threshold", range(1, 6))
    @pytest.mark.parametrize("risk", range(1, 6))
    def test_non_strict(self, threshold, risk):
        gate = RuleGate(threshold=threshold, strict=False)
        result = gate.evaluate(Action(kind="tool_call", name="x", risk=risk))
        if risk <= threshold:
            assert result == GateResult.ALLOWED
        else:
            assert result == GateResult.NEEDS_APPROVAL

    @pytest.mark.parametrize("threshold", range(1, 6))
    @pytest.mark.parametrize("risk", range(1, 6))
    def test_strict(self, threshold, risk):
        gate = RuleGate(threshold=threshold, strict=True)
        result = gate.evaluate(Action(kind="tool_call", name="x", risk=risk))
        if risk <= threshold:
            assert result == GateResult.ALLOWED
        else:
            assert result == GateResult.DENIED


class TestKindThresholds:
    def test_kind_overrides_default_threshold(self):
        gate = RuleGate(threshold=1, kind_thresholds={"tool_call": 3})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=3)) == GateResult.ALLOWED

    def test_unknown_kind_uses_default(self):
        gate = RuleGate(threshold=1, kind_thresholds={"tool_call": 3})
        assert gate.evaluate(Action(kind="file_write", name="x", risk=2)) == GateResult.NEEDS_APPROVAL

    def test_kind_threshold_alias(self):
        gate = RuleGate(threshold=1, kind_thresholds={"tool_call": "standard"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=3)) == GateResult.ALLOWED

    def test_kind_threshold_with_strict(self):
        gate = RuleGate(threshold=1, strict=True, kind_thresholds={"tool_call": 2})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=3)) == GateResult.DENIED

    def test_name_overrides_take_precedence_over_kind(self):
        gate = RuleGate(threshold=1, kind_thresholds={"tool_call": 1}, allowed={"x"})
        assert gate.evaluate(Action(kind="tool_call", name="x", risk=5)) == GateResult.ALLOWED

    def test_multiple_kinds(self):
        gate = RuleGate(
            threshold=1,
            kind_thresholds={"tool_call": 3, "file_write": 2, "code_execution": 1},
        )
        assert gate.evaluate(Action(kind="tool_call", name="a", risk=3)) == GateResult.ALLOWED
        assert gate.evaluate(Action(kind="file_write", name="b", risk=3)) == GateResult.NEEDS_APPROVAL
        assert gate.evaluate(Action(kind="code_execution", name="c", risk=2)) == GateResult.NEEDS_APPROVAL


class TestLabel:
    @pytest.mark.parametrize(("alias", "expected"), [("read-only", "read-only"), ("cautious", "cautious")])
    def test_known_alias(self, alias, expected):
        assert RuleGate(threshold=alias).label == expected

    def test_custom_level(self):
        assert RuleGate(threshold=4).label == "custom (level 4)"
