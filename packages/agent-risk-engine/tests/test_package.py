"""Tests for public API surface."""

import agent_risk_engine


class TestPublicAPI:
    def test_all_names_importable(self):
        for name in agent_risk_engine.__all__:
            assert hasattr(agent_risk_engine, name), f"{name} in __all__ but not importable"

    def test_all_contains_expected_names(self):
        expected = {
            "ActionGate",
            "CallTracker",
            "DEFAULT_PATTERNS",
            "GateResult",
            "NullStateMonitor",
            "PassthroughActionGate",
            "PassthroughAnalyzer",
            "PatternAnalyzer",
            "RiskEvaluator",
            "RiskLevel",
            "RiskPattern",
            "RiskResult",
            "RiskScore",
            "RiskUtilityGate",
            "RuleGate",
            "StateMonitor",
            "SystemState",
            "ToolAnalyzer",
            "ToolDef",
            "ToolRegistry",
            "UtilityScore",
        }
        assert set(agent_risk_engine.__all__) == expected
