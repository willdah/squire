"""Tests for the risk gate factory (create_risk_gate)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_risk_engine import RiskEvaluator, RuleGate

from squire.approval import ApprovalProvider, DenyAllApproval
from squire.callbacks.risk_gate import create_risk_gate


def _make_tool(name: str):
    tool = MagicMock()
    tool.name = name
    return tool


class _FakeState:
    """Dict-like state that supports both .get() and [] access."""

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value


def _make_context(threshold=3, evaluator=None):
    if evaluator is None:
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=threshold))
    ctx = MagicMock()
    ctx.state = _FakeState({"risk_evaluator": evaluator, "risk_tolerance": threshold})
    return ctx


class TestBasicGating:
    @pytest.mark.asyncio
    async def test_allows_tool_below_threshold(self):
        gate = create_risk_gate(tool_risk_levels={"system_info": 1})
        result = await gate(_make_tool("system_info"), {}, _make_context(threshold=3))
        assert result is None

    @pytest.mark.asyncio
    async def test_needs_approval_above_threshold_no_provider(self):
        gate = create_risk_gate(tool_risk_levels={"run_command": 5})
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=2))
        assert result is not None
        assert "auto-denied" in result["error"].lower() or "no approval" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_approval_provider_approves(self):
        provider = MagicMock(spec=ApprovalProvider)
        provider.request_approval.return_value = True
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            approval_provider=provider,
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=2))
        assert result is None
        provider.request_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_provider_denies(self):
        provider = MagicMock(spec=ApprovalProvider)
        provider.request_approval.return_value = False
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            approval_provider=provider,
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=2))
        assert result is not None
        assert "declined" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_deny_all_approval(self):
        provider = DenyAllApproval()
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            approval_provider=provider,
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=2))
        assert result is not None
        assert "declined" in result["error"].lower()


class TestADKInternalTools:
    @pytest.mark.asyncio
    async def test_transfer_to_agent_always_allowed(self):
        gate = create_risk_gate(tool_risk_levels={"system_info": 1})
        result = await gate(_make_tool("transfer_to_agent"), {"agent_name": "Monitor"}, _make_context())
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_tool_denied(self):
        gate = create_risk_gate(tool_risk_levels={"system_info": 1})
        result = await gate(_make_tool("evil_tool"), {}, _make_context())
        assert result is not None
        assert "unknown tool" in result["error"].lower()


class TestHeadlessMode:
    @pytest.mark.asyncio
    async def test_headless_denies_needs_approval(self):
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            headless=True,
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=2))
        assert result is not None
        assert "watch mode" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_headless_allows_below_threshold(self):
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
            headless=True,
        )
        result = await gate(_make_tool("system_info"), {}, _make_context(threshold=3))
        assert result is None

    @pytest.mark.asyncio
    async def test_headless_notifies_on_block(self):
        notifier = AsyncMock()
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            headless=True,
            notifier=notifier,
        )
        await gate(_make_tool("run_command"), {"command": "rm -rf /"}, _make_context(threshold=2))
        notifier.dispatch.assert_called_once()


class TestHostRiskEscalation:
    @pytest.mark.asyncio
    async def test_remote_host_bumps_risk(self):
        # system_info is risk 1, but remote bumps to 2
        # With threshold 1, this should need approval
        gate = create_risk_gate(tool_risk_levels={"system_info": 1})
        result = await gate(
            _make_tool("system_info"),
            {"host": "remote-server"},
            _make_context(threshold=1),
        )
        assert result is not None  # Needs approval / denied

    @pytest.mark.asyncio
    async def test_local_host_no_bump(self):
        gate = create_risk_gate(tool_risk_levels={"system_info": 1})
        result = await gate(
            _make_tool("system_info"),
            {"host": "local"},
            _make_context(threshold=1),
        )
        assert result is None


class TestCompoundActionNames:
    @pytest.mark.asyncio
    async def test_action_param_creates_compound_name(self):
        """Tools with an 'action' param should use 'tool:action' for risk lookup."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:read": 1, "my_tool:write": 4},
        )
        # read action (risk 1) should be allowed at threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "read"},
            _make_context(threshold=3),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_compound_name_high_risk_action_blocked(self):
        """High-risk actions within a tool should be blocked appropriately."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:read": 1, "my_tool:write": 4},
        )
        # write action (risk 4) should need approval at threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "write"},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_action_param_uses_tool_name(self):
        """Tools without an 'action' param should use tool name directly (backward compat)."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
        )
        result = await gate(
            _make_tool("system_info"),
            {"host": "local"},
            _make_context(threshold=3),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_compound_name_remote_host_escalation(self):
        """Remote host escalation should apply to compound action risk levels."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:start": 3},
        )
        # risk 3 + remote bump = 4, which exceeds threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "start", "host": "remote-server"},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_unknown_compound_action_denied(self):
        """An action not in the risk levels dict should be denied."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:read": 1},
        )
        result = await gate(
            _make_tool("my_tool"),
            {"action": "destroy"},
            _make_context(threshold=5),
        )
        assert result is not None
        assert "unknown" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_force_flag_bumps_risk(self):
        """force=True should escalate risk by +1."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:remove": 3},
        )
        # risk 3 + force bump = 4, which exceeds threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "remove", "force": True},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_force_false_no_bump(self):
        """force=False should not escalate risk."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:remove": 3},
        )
        result = await gate(
            _make_tool("my_tool"),
            {"action": "remove", "force": False},
            _make_context(threshold=3),
        )
        assert result is None
