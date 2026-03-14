"""Core data models for the risk evaluation system.

Framework-agnostic — no imports from squire or any agent framework.
"""

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class RiskLevel(IntEnum):
    """Risk level assigned to each tool, 1 (safest) to 5 (most dangerous)."""

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
class RiskScore:
    """Result of a ToolAnalyzer evaluation for a specific tool call."""

    level: int
    reasoning: str = ""
    alternative: str = ""


@dataclass(frozen=True)
class SystemState:
    """Snapshot of system health relevant to risk decisions."""

    healthy: bool = True
    warnings: list[str] = field(default_factory=list)
    risk_adjustment: int = 0


@dataclass(frozen=True)
class UtilityScore:
    """Caller-provided utility estimate for the tool call.

    The library evaluates risk; the calling framework understands
    agent goals and provides utility on the same 1-5 scale.
    """

    level: int  # 1-5, same scale as risk
    reasoning: str = ""


@dataclass(frozen=True)
class RiskResult:
    """Complete result from the RiskEvaluator pipeline."""

    decision: GateResult
    risk_score: RiskScore
    system_state: SystemState
    reasoning: str = ""
    utility: UtilityScore | None = None


@dataclass(frozen=True)
class ToolDef:
    """A registered tool with its static risk level and metadata."""

    name: str
    risk: int
    description: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class RiskPattern:
    """A pattern that indicates a specific risk level when matched in tool arguments."""

    pattern: str
    risk_level: int
    description: str = ""
