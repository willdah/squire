"""Layered risk evaluation for autonomous agent actions.

A framework-agnostic protocol and reference implementation for codifying
risk in agent actions. Zero dependencies.
"""

from .action_gate import ActionGate, PassthroughActionGate, RiskUtilityGate
from .analyzer import DEFAULT_PATTERNS, ActionAnalyzer, PassthroughAnalyzer, PatternAnalyzer
from .assessment import RiskEvaluator
from .call_tracker import CallTracker
from .models import (
    THRESHOLD_ALIASES,
    Action,
    ActionDef,
    GateResult,
    RiskLevel,
    RiskPattern,
    RiskResult,
    RiskScore,
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
