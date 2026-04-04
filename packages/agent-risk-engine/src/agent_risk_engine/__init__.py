"""Layered risk evaluation for AI agent tool execution.

Framework-agnostic — zero dependencies, zero framework imports. Integrate
with any agent framework by writing a thin adapter (~20 lines).
"""

from .action_gate import ActionGate, PassthroughActionGate, RiskUtilityGate
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
from .registry import ActionRegistry
from .rule_gate import RuleGate

__all__ = [
    "Action",
    "ActionDef",
    "ActionGate",
    "ActionRegistry",
    "DEFAULT_PATTERNS",
    "GateResult",
    "PassthroughActionGate",
    "PassthroughAnalyzer",
    "PatternAnalyzer",
    "RiskLevel",
    "RiskPattern",
    "RiskResult",
    "RiskScore",
    "RiskUtilityGate",
    "RuleGate",
    "THRESHOLD_ALIASES",
    "ToolAnalyzer",
    "UtilityScore",
]
