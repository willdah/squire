"""Tests for risk profile gating logic."""

from squire.schemas.risk import GateResult, RiskProfile


class TestBuiltinProfiles:
    def test_readonly_allows_read(self):
        profile = RiskProfile(name="read-only")
        assert profile.gate("system_info", "read") == GateResult.ALLOWED

    def test_readonly_denies_cautious(self):
        profile = RiskProfile(name="read-only")
        assert profile.gate("docker_compose", "cautious") == GateResult.DENIED

    def test_readonly_denies_full(self):
        profile = RiskProfile(name="read-only")
        assert profile.gate("run_command", "full") == GateResult.DENIED

    def test_cautious_allows_read(self):
        profile = RiskProfile(name="cautious")
        assert profile.gate("system_info", "read") == GateResult.ALLOWED

    def test_cautious_allows_cautious(self):
        profile = RiskProfile(name="cautious")
        assert profile.gate("docker_compose", "cautious") == GateResult.ALLOWED

    def test_cautious_requires_approval_for_standard(self):
        profile = RiskProfile(name="cautious")
        assert profile.gate("some_tool", "standard") == GateResult.NEEDS_APPROVAL

    def test_cautious_requires_approval_for_full(self):
        profile = RiskProfile(name="cautious")
        assert profile.gate("run_command", "full") == GateResult.NEEDS_APPROVAL

    def test_standard_allows_standard(self):
        profile = RiskProfile(name="standard")
        assert profile.gate("some_tool", "standard") == GateResult.ALLOWED

    def test_standard_requires_approval_for_full(self):
        profile = RiskProfile(name="standard")
        assert profile.gate("run_command", "full") == GateResult.NEEDS_APPROVAL

    def test_full_trust_allows_everything(self):
        profile = RiskProfile(name="full-trust")
        assert profile.gate("run_command", "full") == GateResult.ALLOWED
        assert profile.gate("system_info", "read") == GateResult.ALLOWED


class TestCustomProfile:
    def test_custom_allowed(self):
        profile = RiskProfile(name="custom", allowed_tools={"docker_ps"})
        assert profile.gate("docker_ps", "read") == GateResult.ALLOWED

    def test_custom_denied(self):
        profile = RiskProfile(name="custom", denied_tools={"run_command"})
        assert profile.gate("run_command", "full") == GateResult.DENIED

    def test_custom_approval(self):
        profile = RiskProfile(name="custom", approval_tools={"docker_compose"})
        assert profile.gate("docker_compose", "cautious") == GateResult.NEEDS_APPROVAL

    def test_custom_unlisted_requires_approval(self):
        profile = RiskProfile(name="custom", allowed_tools={"docker_ps"})
        assert profile.gate("unknown_tool", "read") == GateResult.NEEDS_APPROVAL

    def test_custom_denied_takes_precedence(self):
        profile = RiskProfile(
            name="custom",
            allowed_tools={"run_command"},
            denied_tools={"run_command"},
        )
        assert profile.gate("run_command", "full") == GateResult.DENIED


class TestRiskProfileSerialization:
    def test_roundtrip(self):
        profile = RiskProfile(name="cautious")
        data = profile.model_dump()
        restored = RiskProfile.model_validate(data)
        assert restored.name == "cautious"
        assert restored.gate("system_info", "read") == GateResult.ALLOWED
