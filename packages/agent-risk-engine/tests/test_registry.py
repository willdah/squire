"""Tests for ToolRegistry."""

import pytest

from agent_risk_engine.models import ToolDef
from agent_risk_engine.registry import ToolRegistry


class TestRegistration:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = reg.register("read_file", 1, description="Read a file")
        assert isinstance(tool, ToolDef)
        assert tool.name == "read_file"
        assert tool.risk == 1
        assert tool.description == "Read a file"

    def test_register_with_tags(self):
        reg = ToolRegistry()
        tool = reg.register("deploy", 5, tags=frozenset({"infra", "prod"}))
        assert tool.tags == frozenset({"infra", "prod"})

    def test_get_returns_none_for_unknown(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_register_overwrites(self):
        reg = ToolRegistry()
        reg.register("tool", 1)
        reg.register("tool", 5)
        assert reg.get_risk("tool") == 5


class TestRiskLookup:
    def test_get_risk_registered(self):
        reg = ToolRegistry()
        reg.register("read_file", 1)
        assert reg.get_risk("read_file") == 1

    def test_get_risk_unknown_returns_default(self):
        reg = ToolRegistry(default_risk=5)
        assert reg.get_risk("unknown") == 5

    def test_custom_default_risk(self):
        reg = ToolRegistry(default_risk=3)
        assert reg.get_risk("unknown") == 3


class TestContainerProtocol:
    def test_contains(self):
        reg = ToolRegistry()
        reg.register("tool", 1)
        assert "tool" in reg
        assert "other" not in reg

    def test_len(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register("a", 1)
        reg.register("b", 2)
        assert len(reg) == 2
