"""Layered risk evaluation for AI agent tool execution.

Framework-agnostic — zero dependencies, zero framework imports. Integrate
with any agent framework by writing a thin adapter (~20 lines).
"""

from .action_gate import ActionGate, PassthroughActionGate, RiskUtilityGate
from .analyzer import ActionAnalyzer, DEFAULT_PATTERNS, PassthroughAnalyzer, PatternAnalyzer
from .assessment import RiskEvaluator
from .call_tracker import CallTracker
from .models import (
    Action,
    ActionDef,
    GateResult,
    RiskLevel,
    RiskPattern,
    RiskResult,
    RiskScore,
    THRESHOLD_ALIASES,
    UtilityScore,
)
from .registry import ActionRegistry
from .rule_gate import RuleGate

__all__ = [
    "Action",
    "ActionAnalyzer",
    "ActionDef",
    "ActionGate",
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
]
