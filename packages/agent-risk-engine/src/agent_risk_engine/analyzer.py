"""ActionAnalyzer — Layer 2: Argument-aware risk analysis.

Protocol, stub, and pattern-based implementation.
Framework-agnostic — no external dependencies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from .models import RiskPattern, RiskScore

if TYPE_CHECKING:
    from .models import Action

DEFAULT_PATTERNS: list[RiskPattern] = [
    RiskPattern(r"\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r|--force|--recursive)", 5, "Recursive/forced file deletion"),
    RiskPattern(r"\bmkfs\b", 5, "Filesystem formatting"),
    RiskPattern(r"\bdd\s+if=", 5, "Raw disk write"),
    RiskPattern(r"\bcurl\b.*\|\s*(bash|sh)\b", 5, "Pipe remote script to shell"),
    RiskPattern(r"\bwget\b.*\|\s*(bash|sh)\b", 5, "Pipe remote script to shell"),
    RiskPattern(r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", 5, "SQL drop operation"),
    RiskPattern(r"\bTRUNCATE\s+", 5, "SQL truncate"),
    RiskPattern(r"\bDELETE\s+FROM\b", 4, "SQL delete"),
    RiskPattern(r"\bALTER\s+TABLE\b", 3, "SQL schema modification"),
    RiskPattern(r"/etc/|/usr/|/sys/|/proc/|/boot/", 4, "Sensitive system path"),
    RiskPattern(r"C:\\Windows|C:\\System32", 4, "Sensitive Windows path"),
    RiskPattern(r"\.(env|pem|key|crt|p12|pfx)\b", 4, "Sensitive file type"),
    RiskPattern(r"\bsudo\b", 4, "Privilege escalation"),
    RiskPattern(r"\bchmod\s+777\b", 4, "World-writable permissions"),
    RiskPattern(r"\bchown\b", 3, "Ownership change"),
    RiskPattern(r"--no-backup|--force|--no-preserve", 3, "Safety bypass flag"),
]


class ActionAnalyzer(Protocol):
    """Analyzes the actual risk of a specific action based on its parameters."""

    async def analyze(self, action: Action) -> RiskScore:
        """Evaluate the risk of an action with its specific parameters."""
        ...


class PassthroughAnalyzer:
    """Stub analyzer that returns the action's static risk level unchanged."""

    async def analyze(self, action: Action) -> RiskScore:
        return RiskScore(level=action.risk)


class PatternAnalyzer:
    """Argument-aware risk analysis using regex pattern matching.

    Scans action parameters for patterns indicating risk. Can only escalate
    risk, never reduce it below the static action risk.
    """

    def __init__(
        self,
        extra_patterns: list[RiskPattern] | None = None,
        include_defaults: bool = True,
    ) -> None:
        base = list(DEFAULT_PATTERNS) if include_defaults else []
        self._patterns = base + (extra_patterns or [])

    async def analyze(self, action: Action) -> RiskScore:
        text = _flatten_args(action.parameters)
        if not text:
            return RiskScore(level=action.risk)

        matches: list[RiskPattern] = []
        for p in self._patterns:
            if p.kinds is not None and action.kind not in p.kinds:
                continue
            if re.search(p.pattern, text, re.IGNORECASE):
                matches.append(p)

        if not matches:
            return RiskScore(level=action.risk)

        worst = max(matches, key=lambda p: p.risk_level)
        assessed = max(action.risk, worst.risk_level)
        reasons = [m.description for m in sorted(matches, key=lambda m: -m.risk_level)]

        return RiskScore(level=assessed, reasoning="; ".join(reasons))


def _flatten_args(args: dict) -> str:
    """Flatten a parameters dict into a single string for pattern matching."""
    parts: list[str] = []
    for v in args.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(item) for item in v)
        else:
            parts.append(str(v))
    return " ".join(parts)
