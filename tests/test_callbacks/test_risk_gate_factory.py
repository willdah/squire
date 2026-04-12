"""Tests for the risk gate factory (create_risk_gate)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_risk_engine import GateResult, RiskEvaluator, RuleGate

from squire.approval import ApprovalProvider, AsyncApprovalProvider, DenyAllApproval
from squire.callbacks.risk_gate import HOMELAB_PATTERNS, build_pattern_analyzer, create_risk_gate
from squire.watch_autonomy import action_signature


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
    async def test_async_approval_provider_approves(self):
        class _AsyncProvider:
            async def request_approval_async(self, tool_name, args, risk_level):
                return True

        provider = _AsyncProvider()
        assert isinstance(provider, AsyncApprovalProvider)
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            approval_provider=provider,
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=2))
        assert result is None

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

    @pytest.mark.asyncio
    async def test_fallback_to_bare_tool_name(self):
        """Tools with action param but no compound entries should fall back to bare tool name."""
        gate = create_risk_gate(
            tool_risk_levels={"docker_compose": 3},
        )
        # Simulates a tool with an action param but only a bare-name risk entry
        result = await gate(
            _make_tool("docker_compose"),
            {"action": "ps"},
            _make_context(threshold=3),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_still_blocks_unknown_tool(self):
        """Unknown tool with action param should still be blocked (no fallback)."""
        gate = create_risk_gate(
            tool_risk_levels={"docker_compose": 3},
        )
        result = await gate(
            _make_tool("unknown_tool"),
            {"action": "ps"},
            _make_context(threshold=5),
        )
        assert result is not None
        assert "unknown" in result["error"].lower()


class TestRiskOverrides:
    @pytest.mark.asyncio
    async def test_override_lowers_risk(self):
        """A risk override should substitute the base risk level."""
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            risk_overrides={"run_command": 1},
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=3))
        assert result is None  # risk 1 <= threshold 3

    @pytest.mark.asyncio
    async def test_override_raises_risk(self):
        """A risk override can raise the risk above threshold."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
            risk_overrides={"system_info": 5},
        )
        result = await gate(_make_tool("system_info"), {}, _make_context(threshold=3))
        assert result is not None  # risk 5 > threshold 3

    @pytest.mark.asyncio
    async def test_override_compound_action(self):
        """Risk overrides work with compound action names."""
        gate = create_risk_gate(
            tool_risk_levels={"docker_container:remove": 4},
            risk_overrides={"docker_container:remove": 1},
        )
        result = await gate(
            _make_tool("docker_container"),
            {"action": "remove"},
            _make_context(threshold=3),
        )
        assert result is None  # overridden to risk 1

    @pytest.mark.asyncio
    async def test_override_only_affects_specified_tool(self):
        """An override for one tool should not affect another."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1, "run_command": 5},
            risk_overrides={"run_command": 1},
        )
        # system_info should still use its base risk of 1
        result = await gate(_make_tool("system_info"), {}, _make_context(threshold=3))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_overrides_is_default_behavior(self):
        """When risk_overrides is None/empty, behavior is unchanged."""
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            risk_overrides={},
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=3))
        assert result is not None  # risk 5 > threshold 3

    @pytest.mark.asyncio
    async def test_remote_host_still_bumps_after_override(self):
        """Remote host escalation should apply on top of the override."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
            risk_overrides={"system_info": 3},
        )
        # Override to 3, remote bump to 4, threshold 3 → needs approval
        result = await gate(
            _make_tool("system_info"),
            {"host": "remote-server"},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_default_threshold_takes_precedence_over_state_threshold(self):
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 4},
            default_threshold=5,
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=1))
        assert result is None


class TestWatchCooldown:
    @pytest.mark.asyncio
    async def test_watch_blocked_action_signature_denies_repeated_action(self):
        gate = create_risk_gate(tool_risk_levels={"docker_container:restart": 2})
        ctx = _make_context(threshold=3)
        args = {"action": "restart", "host": "local"}
        ctx.state["watch_blocked_action_signatures"] = {action_signature("docker_container", args)}
        result = await gate(_make_tool("docker_container"), args, ctx)
        assert result is not None
        assert "watch cooldown" in result["error"].lower()


class TestPatternAnalyzerIntegration:
    """Tests for PatternAnalyzer replacing PassthroughAnalyzer in the risk pipeline."""

    def test_build_pattern_analyzer_includes_defaults_and_homelab(self):
        """build_pattern_analyzer should include both default and homelab patterns."""
        analyzer = build_pattern_analyzer()
        # _patterns is a list of RiskPattern; homelab patterns are appended to defaults
        assert len(analyzer._patterns) > len(HOMELAB_PATTERNS)

    @pytest.mark.asyncio
    async def test_dangerous_command_escalates_risk(self):
        """A low-risk tool with dangerous args should be escalated by PatternAnalyzer."""
        # run_command has static risk 2, but "rm -rf /" matches a default pattern at risk 5
        analyzer = build_pattern_analyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3), analyzer=analyzer)
        gate = create_risk_gate(tool_risk_levels={"run_command": 2})
        ctx = _make_context(threshold=3, evaluator=evaluator)
        result = await gate(_make_tool("run_command"), {"command": "rm -rf /tmp/data"}, ctx)
        assert result is not None
        assert "blocked" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_safe_command_not_escalated(self):
        """A low-risk tool with safe args should not be escalated."""
        analyzer = build_pattern_analyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3), analyzer=analyzer)
        gate = create_risk_gate(tool_risk_levels={"run_command": 2})
        ctx = _make_context(threshold=3, evaluator=evaluator)
        result = await gate(_make_tool("run_command"), {"command": "ls -la /home"}, ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_privileged_flag_escalates(self):
        """Homelab pattern: --privileged flag should escalate risk."""
        analyzer = build_pattern_analyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3), analyzer=analyzer)
        gate = create_risk_gate(tool_risk_levels={"run_command": 2})
        ctx = _make_context(threshold=3, evaluator=evaluator)
        result = await gate(_make_tool("run_command"), {"command": "docker run --privileged nginx"}, ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_firewall_modification_escalates(self):
        """Homelab pattern: firewall commands should escalate risk."""
        analyzer = build_pattern_analyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3), analyzer=analyzer)
        gate = create_risk_gate(tool_risk_levels={"run_command": 2})
        ctx = _make_context(threshold=3, evaluator=evaluator)
        result = await gate(_make_tool("run_command"), {"command": "ufw allow 8080"}, ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_sensitive_file_type_escalates(self):
        """Default pattern: .env file access should escalate risk."""
        analyzer = build_pattern_analyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3), analyzer=analyzer)
        gate = create_risk_gate(tool_risk_levels={"read_config": 2})
        ctx = _make_context(threshold=3, evaluator=evaluator)
        result = await gate(_make_tool("read_config"), {"path": "/app/.env"}, ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_sudo_escalates(self):
        """Default pattern: sudo should escalate risk."""
        analyzer = build_pattern_analyzer()
        evaluator = RiskEvaluator(rule_gate=RuleGate(threshold=3), analyzer=analyzer)
        gate = create_risk_gate(tool_risk_levels={"run_command": 2})
        ctx = _make_context(threshold=3, evaluator=evaluator)
        result = await gate(_make_tool("run_command"), {"command": "sudo systemctl restart nginx"}, ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_fallback_evaluator_uses_pattern_analyzer(self):
        """When no evaluator is in session state, the fallback should use PatternAnalyzer."""
        gate = create_risk_gate(tool_risk_levels={"run_command": 2})
        # Context with no evaluator — forces fallback
        ctx = MagicMock()
        ctx.state = _FakeState({"risk_evaluator": None, "risk_tolerance": 3})
        # "rm -rf" should be caught by the fallback PatternAnalyzer
        result = await gate(_make_tool("run_command"), {"command": "rm -rf /data"}, ctx)
        assert result is not None
        assert "blocked" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_analyzer_escalated_allowed_result_requests_approval(self, monkeypatch):
        class _FakeScore:
            level = 5

        class _FakeResult:
            decision = GateResult.ALLOWED
            risk_score = _FakeScore()
            reasoning = "escalated"

        class _FakeEvaluator:
            def __init__(self):
                self.rule_gate = RuleGate(threshold=3)

            async def evaluate(self, action):
                return _FakeResult()

        monkeypatch.setattr(
            "squire.callbacks.risk_gate._build_evaluator_from_state",
            lambda tool_context, default_threshold=None: _FakeEvaluator(),
        )
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 1},
            approval_provider=DenyAllApproval(),
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=5))
        assert result is not None
        assert "declined" in result["error"].lower()
