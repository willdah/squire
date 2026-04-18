"""Tests for tool effect classification (read / write / mixed)."""

import pytest

from squire.tools import ALL_TOOLS, TOOL_EFFECTS, TOOL_RISK_LEVELS, get_tool_effect
from squire.tools._effects import derive_effect


def test_every_tool_has_effect():
    """Registry completeness — adding a tool without EFFECT/EFFECTS must fail."""
    tool_names = {t.__name__ for t in ALL_TOOLS}
    assert tool_names == set(TOOL_EFFECTS.keys())


def test_multi_action_effects_cover_all_actions():
    """Every ``tool:action`` risk entry has a matching effect on the same action."""
    for key in TOOL_RISK_LEVELS:
        if ":" not in key:
            continue
        tool, action = key.split(":", 1)
        entry = TOOL_EFFECTS[tool]
        assert isinstance(entry, dict), f"{tool} has per-action risks but flat effect"
        assert action in entry, f"{tool}:{action} missing from EFFECTS"


def test_single_action_tools_have_scalar_effect():
    """Tools without per-action risks should map to a scalar Effect (read/write/mixed)."""
    multi_tool_names = {key.split(":", 1)[0] for key in TOOL_RISK_LEVELS if ":" in key}
    for tool_name, entry in TOOL_EFFECTS.items():
        if tool_name in multi_tool_names:
            assert isinstance(entry, dict)
        else:
            assert isinstance(entry, str)
            assert entry in {"read", "write", "mixed"}


class TestDeriveEffect:
    def test_all_read(self):
        assert derive_effect({"a": "read", "b": "read"}) == "read"

    def test_all_write(self):
        assert derive_effect({"a": "write", "b": "write"}) == "write"

    def test_mixed(self):
        assert derive_effect({"a": "read", "b": "write"}) == "mixed"

    def test_explicit_mixed_collapses_to_mixed(self):
        assert derive_effect({"a": "mixed"}) == "mixed"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            derive_effect({})


class TestGetToolEffect:
    def test_read_only_tool(self):
        assert get_tool_effect("system_info") == "read"
        assert get_tool_effect("docker_ps") == "read"
        assert get_tool_effect("journalctl") == "read"

    def test_all_read_multi_action_tool(self):
        # docker_volume has only list/inspect actions — both read
        assert get_tool_effect("docker_volume") == "read"
        assert get_tool_effect("docker_network") == "read"

    def test_mixed_multi_action_tool(self):
        assert get_tool_effect("docker_container") == "mixed"
        assert get_tool_effect("systemctl") == "mixed"

    def test_run_command_is_mixed(self):
        assert get_tool_effect("run_command") == "mixed"
