"""Tests for alert rule condition parsing and evaluation."""

import pytest

from squire.notifications.conditions import (
    ConditionError,
    evaluate_condition,
    parse_condition,
)


class TestParseCondition:
    def test_simple_greater_than(self):
        c = parse_condition("cpu_percent > 90")
        assert c.field == "cpu_percent"
        assert c.op_str == ">"
        assert c.value == 90

    def test_greater_equal(self):
        c = parse_condition("memory_used_mb >= 14000")
        assert c.field == "memory_used_mb"
        assert c.op_str == ">="
        assert c.value == 14000

    def test_less_than(self):
        c = parse_condition("disk_free_gb < 10")
        assert c.field == "disk_free_gb"
        assert c.op_str == "<"
        assert c.value == 10

    def test_equal(self):
        c = parse_condition("state == running")
        assert c.field == "state"
        assert c.op_str == "=="
        assert c.value == "running"

    def test_not_equal(self):
        c = parse_condition("state != running")
        assert c.op_str == "!="

    def test_float_value(self):
        c = parse_condition("cpu_percent > 85.5")
        assert c.value == 85.5

    def test_dotted_field(self):
        c = parse_condition("containers.nginx.state == exited")
        assert c.field == "containers.nginx.state"

    def test_whitespace_tolerance(self):
        c = parse_condition("  cpu_percent   >   90  ")
        assert c.field == "cpu_percent"
        assert c.value == 90

    def test_invalid_condition_raises(self):
        with pytest.raises(ConditionError):
            parse_condition("not a valid condition")

    def test_empty_string_raises(self):
        with pytest.raises(ConditionError):
            parse_condition("")

    def test_missing_operator_raises(self):
        with pytest.raises(ConditionError):
            parse_condition("cpu_percent 90")

    def test_repr(self):
        c = parse_condition("cpu_percent > 90")
        assert repr(c) == "cpu_percent > 90"


class TestEvaluateCondition:
    def test_greater_than_true(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {"cpu_percent": 95}) is True

    def test_greater_than_false(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {"cpu_percent": 50}) is False

    def test_equal_boundary(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {"cpu_percent": 90}) is False

    def test_greater_equal_boundary(self):
        c = parse_condition("cpu_percent >= 90")
        assert evaluate_condition(c, {"cpu_percent": 90}) is True

    def test_string_equality(self):
        c = parse_condition("state == running")
        assert evaluate_condition(c, {"state": "running"}) is True
        assert evaluate_condition(c, {"state": "exited"}) is False

    def test_missing_field_returns_false(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {"memory_used_mb": 8000}) is False

    def test_empty_snapshot_returns_false(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {}) is False

    def test_nested_field(self):
        c = parse_condition("disk.percent > 80")
        snapshot = {"disk": {"percent": 92}}
        assert evaluate_condition(c, snapshot) is True

    def test_type_coercion_string_to_float(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {"cpu_percent": "95"}) is True

    def test_incompatible_types_returns_false(self):
        c = parse_condition("cpu_percent > 90")
        assert evaluate_condition(c, {"cpu_percent": "not_a_number"}) is False
