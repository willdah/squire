"""Core data models for the risk evaluation protocol.

Framework-agnostic — no external dependencies.
"""

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class RiskLevel(IntEnum):
    """Risk level assigned to each action, 1 (safest) to 5 (most dangerous)."""

    INFO = 1
    LOW = 2
    MODERATE = 3
    HIGH = 4
    CRITICAL = 5

    @property
    def label(self) -> str:
        return self.name.capitalize()


class GateResult(StrEnum):
    """Outcome of a risk gate evaluation."""

    ALLOWED = "allowed"
    NEEDS_APPROVAL = "needs_approval"
    DENIED = "denied"


THRESHOLD_ALIASES: dict[str, int] = {
    "read-only": 1,
    "cautious": 2,
    "standard": 3,
    "full-trust": 5,
}


@dataclass(frozen=True)
class Action:
    """Self-describing action envelope for risk evaluation.

    Represents any operation an agent can take — tool calls, file writes,
    API requests, code execution, etc.
    """

    kind: str
    name: str
    parameters: dict = field(default_factory=dict)
    risk: int = 5
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ActionDef:
    """A registered action with its static risk level and metadata."""

    name: str
    kind: str
    risk: int
    description: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class RiskScore:
    """Result of an ActionAnalyzer evaluation."""

    level: int
    reasoning: str = ""


@dataclass(frozen=True)
class UtilityScore:
    """Caller-provided utility estimate for the action.

    The library evaluates risk; the calling framework understands
    agent goals and provides utility on the same 1-5 scale.
    """

    level: int
    reasoning: str = ""


@dataclass(frozen=True)
class RiskResult:
    """Complete result from the RiskEvaluator pipeline."""

    decision: GateResult
    risk_score: RiskScore
    reasoning: str = ""
    utility: UtilityScore | None = None


@dataclass(frozen=True)
class RiskPattern:
    """A pattern that indicates a specific risk level when matched in action parameters."""

    pattern: str
    risk_level: int
    description: str = ""
    kinds: frozenset[str] | None = None
