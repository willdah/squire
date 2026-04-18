"""Tests for the GET /api/tools endpoint."""

from squire.api.routers.tools import _build_tool_catalog
from squire.config import GuardrailsConfig


class TestBuildToolCatalog:
    def test_returns_all_tools(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        names = {t.name for t in tools}
        assert "system_info" in names
        assert "docker_container" in names
        assert "run_command" in names
        assert "docker_volume" in names
        assert "docker_network" in names
        assert len(tools) == 14  # all registered tools

    def test_single_action_tool_has_risk_level(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.risk_level == 1
        assert si.actions is None
        assert si.risk_override is None

    def test_multi_action_tool_has_actions(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        dc = next(t for t in tools if t.name == "docker_container")
        assert dc.actions is not None
        assert dc.risk_level is None  # multi-action: risk is on actions
        action_names = {a.name for a in dc.actions}
        assert action_names == {"inspect", "start", "stop", "restart", "remove"}
        inspect_action = next(a for a in dc.actions if a.name == "inspect")
        assert inspect_action.risk_level == 1
        remove_action = next(a for a in dc.actions if a.name == "remove")
        assert remove_action.risk_level == 4

    def test_tool_groups_assigned(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        groups = {t.name: t.group for t in tools}
        assert groups["system_info"] == "monitor"
        assert groups["docker_container"] == "container"
        assert groups["run_command"] == "admin"

    def test_parameters_extracted(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        param_names = {p.name for p in si.parameters}
        assert "host" in param_names
        host_param = next(p for p in si.parameters if p.name == "host")
        assert host_param.required is False
        assert host_param.default == "local"

    def test_denied_tool_shows_disabled(self):
        guardrails = GuardrailsConfig(tools_deny=["run_command"])
        tools = _build_tool_catalog(guardrails)
        rc = next(t for t in tools if t.name == "run_command")
        assert rc.status == "disabled"

    def test_approval_policy_always(self):
        guardrails = GuardrailsConfig(tools_require_approval=["run_command"])
        tools = _build_tool_catalog(guardrails)
        rc = next(t for t in tools if t.name == "run_command")
        assert rc.approval_policy == "always"

    def test_approval_policy_never(self):
        guardrails = GuardrailsConfig(tools_allow=["system_info"])
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.approval_policy == "never"

    def test_risk_override_single_action(self):
        guardrails = GuardrailsConfig(tools_risk_overrides={"system_info": 3})
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.risk_level == 1  # base unchanged
        assert si.risk_override == 3

    def test_risk_override_multi_action(self):
        guardrails = GuardrailsConfig(tools_risk_overrides={"docker_container:remove": 5})
        tools = _build_tool_catalog(guardrails)
        dc = next(t for t in tools if t.name == "docker_container")
        remove = next(a for a in dc.actions if a.name == "remove")
        assert remove.risk_level == 4  # base unchanged
        assert remove.risk_override == 5
        # Other actions should not have override
        inspect_action = next(a for a in dc.actions if a.name == "inspect")
        assert inspect_action.risk_override is None

    def test_default_approval_is_none(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.approval_policy is None

    def test_description_is_first_line(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert "system information" in si.description.lower()
        assert "\n" not in si.description


class TestEffect:
    def test_every_tool_has_effect(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        for t in tools:
            assert t.effect in {"read", "write", "mixed"}

    def test_single_action_read_tool(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.effect == "read"

    def test_run_command_is_mixed(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        rc = next(t for t in tools if t.name == "run_command")
        assert rc.effect == "mixed"

    def test_multi_action_tool_effect_derived_mixed(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        dc = next(t for t in tools if t.name == "docker_container")
        assert dc.effect == "mixed"  # inspect=read, start/stop/... = write

    def test_multi_action_all_read_tool_effect(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        dv = next(t for t in tools if t.name == "docker_volume")
        assert dv.effect == "read"  # only list and inspect

    def test_per_action_effect_present(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        dc = next(t for t in tools if t.name == "docker_container")
        by_name = {a.name: a.effect for a in dc.actions}
        assert by_name["inspect"] == "read"
        assert by_name["remove"] == "write"
        assert by_name["start"] == "write"
