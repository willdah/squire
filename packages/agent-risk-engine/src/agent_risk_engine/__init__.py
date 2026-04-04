"""Layered risk evaluation for AI agent tool execution.

Framework-agnostic — zero dependencies, zero framework imports. Integrate
with any agent framework by writing a thin adapter (~20 lines).
"""

from .analyzer import DEFAULT_PATTERNS, PassthroughAnalyzer, PatternAnalyzer, ToolAnalyzer
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
from .rule_gate import RuleGate

__all__ = [
    "Action",
    "ActionDef",
    "DEFAULT_PATTERNS",
    "GateResult",
    "PassthroughAnalyzer",
    "PatternAnalyzer",
    "RiskLevel",
    "RiskPattern",
    "RiskResult",
    "RiskScore",
    "RuleGate",
    "THRESHOLD_ALIASES",
    "ToolAnalyzer",
    "UtilityScore",
]
