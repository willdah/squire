"""Tests for ActionRegistry."""

from agent_risk_engine import ActionDef, ActionRegistry


class TestRegistration:
    def test_register_and_get(self):
        reg = ActionRegistry()
        result = reg.register("read_file", "tool_call", 1, description="Read a file")
        assert isinstance(result, ActionDef)
        assert result.name == "read_file"
        assert result.kind == "tool_call"
        assert result.risk == 1
        assert result.description == "Read a file"
        assert reg.get("read_file") == result

    def test_register_with_tags(self):
        reg = ActionRegistry()
        result = reg.register("x", "tool_call", 2, tags=frozenset({"safe"}))
        assert result.tags == frozenset({"safe"})

    def test_get_returns_none_for_unknown(self):
        reg = ActionRegistry()
        assert reg.get("unknown") is None

    def test_register_overwrites(self):
        reg = ActionRegistry()
        reg.register("x", "tool_call", 1)
        reg.register("x", "api_request", 3)
        assert reg.get("x").risk == 3
        assert reg.get("x").kind == "api_request"


class TestRiskLookup:
    def test_get_risk_registered(self):
        reg = ActionRegistry()
        reg.register("x", "tool_call", 3)
        assert reg.get_risk("x") == 3

    def test_get_risk_unknown_returns_default(self):
        reg = ActionRegistry()
        assert reg.get_risk("unknown") == 5

    def test_custom_default_risk(self):
        reg = ActionRegistry(default_risk=3)
        assert reg.get_risk("unknown") == 3


class TestContainerProtocol:
    def test_contains(self):
        reg = ActionRegistry()
        reg.register("x", "tool_call", 1)
        assert "x" in reg
        assert "y" not in reg

    def test_len(self):
        reg = ActionRegistry()
        assert len(reg) == 0
        reg.register("a", "tool_call", 1)
        reg.register("b", "file_write", 2)
        assert len(reg) == 2
