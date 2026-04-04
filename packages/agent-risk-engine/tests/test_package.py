"""Tests for public API surface."""

import agent_risk_engine


class TestPublicAPI:
    def test_all_names_importable(self):
        for name in agent_risk_engine.__all__:
            assert hasattr(agent_risk_engine, name), f"{name} in __all__ but not importable"

    def test_all_contains_expected_names(self):
        expected = {
            "ActionAnalyzer",
            "ActionGate",
            "Action",
            "ActionDef",
            "ActionRegistry",
            "CallTracker",
            "DEFAULT_PATTERNS",
            "GateResult",
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
            "THRESHOLD_ALIASES",
            "UtilityScore",
        }
        assert set(agent_risk_engine.__all__) == expected
