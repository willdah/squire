"""Tests for multi-agent tree structure and wiring."""

import pytest

from squire.agents.squire_agent import create_squire_agent
from squire.callbacks.risk_gate import create_risk_gate
from squire.config import AppConfig
from squire.tools import TOOL_RISK_LEVELS


def _make_factory():
    return lambda trl: create_risk_gate(tool_risk_levels=trl)


class TestSingleAgentMode:
    def test_creates_single_agent(self):
        config = AppConfig(multi_agent=False)
        agent = create_squire_agent(app_config=config)
        assert agent.name == "Squire"
        assert len(agent.sub_agents) == 0
        assert len(agent.tools) == 14

    def test_explicit_callback(self):
        config = AppConfig(multi_agent=False)
        cb = create_risk_gate(tool_risk_levels=TOOL_RISK_LEVELS)
        agent = create_squire_agent(app_config=config, before_tool_callback=cb)
        assert agent.before_tool_callback is cb


class TestMultiAgentMode:
    def test_creates_four_sub_agents(self):
        config = AppConfig(multi_agent=True)
        agent = create_squire_agent(
            app_config=config,
            risk_gate_factory=_make_factory(),
        )
        assert agent.name == "Squire"
        assert len(agent.sub_agents) == 4
        assert len(agent.tools) == 0

    def test_sub_agent_names(self):
        config = AppConfig(multi_agent=True)
        agent = create_squire_agent(
            app_config=config,
            risk_gate_factory=_make_factory(),
        )
        names = {sa.name for sa in agent.sub_agents}
        assert names == {"Monitor", "Container", "Admin", "Notifier"}

    def test_sub_agents_have_callbacks(self):
        config = AppConfig(multi_agent=True)
        agent = create_squire_agent(
            app_config=config,
            risk_gate_factory=_make_factory(),
        )
        for sa in agent.sub_agents:
            assert sa.before_tool_callback is not None, f"{sa.name} missing callback"

    def test_each_sub_agent_has_unique_tools(self):
        """Sub-agents must not wire the same tool twice; sharing across agents is allowed."""
        config = AppConfig(multi_agent=True)
        agent = create_squire_agent(
            app_config=config,
            risk_gate_factory=_make_factory(),
        )
        for sa in agent.sub_agents:
            names = [tool.__name__ if hasattr(tool, "__name__") else str(tool) for tool in sa.tools]
            assert len(names) == len(set(names)), f"{sa.name} has duplicate tools: {names}"

    def test_sub_agent_tool_counts(self):
        config = AppConfig(multi_agent=True)
        agent = create_squire_agent(
            app_config=config,
            risk_gate_factory=_make_factory(),
        )
        tool_counts = {sa.name: len(sa.tools) for sa in agent.sub_agents}
        assert tool_counts == {"Monitor": 5, "Container": 8, "Admin": 2, "Notifier": 5}

    def test_requires_risk_gate_factory(self):
        config = AppConfig(multi_agent=True)
        with pytest.raises(ValueError, match="risk_gate_factory"):
            create_squire_agent(app_config=config)

    def test_sub_agents_have_descriptions(self):
        config = AppConfig(multi_agent=True)
        agent = create_squire_agent(
            app_config=config,
            risk_gate_factory=_make_factory(),
        )
        for sa in agent.sub_agents:
            assert sa.description, f"{sa.name} missing description"
