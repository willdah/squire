"""ToolAnalyzer — Layer 2: Argument-aware risk analysis.

Protocol, stub, and pattern-based implementation.
Framework-agnostic — no imports from squire or any agent framework.
"""

import re
from typing import Protocol

from .models import RiskPattern, RiskScore

# --- Default risk patterns ---

DEFAULT_PATTERNS: list[RiskPattern] = [
    # Destructive shell commands
    RiskPattern(
        r"\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r|--force|--recursive)",
        5,
        "Recursive/forced file deletion",
    ),
    RiskPattern(r"\bmkfs\b", 5, "Filesystem formatting"),
    RiskPattern(r"\bdd\s+if=", 5, "Raw disk write"),
    RiskPattern(r"\bcurl\b.*\|\s*(bash|sh)\b", 5, "Pipe remote script to shell"),
    RiskPattern(r"\bwget\b.*\|\s*(bash|sh)\b", 5, "Pipe remote script to shell"),
    # SQL destructive operations
    RiskPattern(r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", 5, "SQL drop operation"),
    RiskPattern(r"\bTRUNCATE\s+", 5, "SQL truncate"),
    RiskPattern(r"\bDELETE\s+FROM\b", 4, "SQL delete"),
    RiskPattern(r"\bALTER\s+TABLE\b", 3, "SQL schema modification"),
    # Sensitive filesystem paths
    RiskPattern(r"/etc/|/usr/|/sys/|/proc/|/boot/", 4, "Sensitive system path"),
    RiskPattern(r"C:\\Windows|C:\\System32", 4, "Sensitive Windows path"),
    RiskPattern(r"\.(env|pem|key|crt|p12|pfx)\b", 4, "Sensitive file type"),
    # Privilege escalation
    RiskPattern(r"\bsudo\b", 4, "Privilege escalation"),
    RiskPattern(r"\bchmod\s+777\b", 4, "World-writable permissions"),
    RiskPattern(r"\bchown\b", 3, "Ownership change"),
    # Safety bypass flags
    RiskPattern(r"--no-backup|--force|--no-preserve", 3, "Safety bypass flag"),
]


class ToolAnalyzer(Protocol):
    """Analyzes the actual risk of a specific tool call based on its arguments."""

    async def analyze(self, tool_name: str, args: dict, tool_risk: int) -> RiskScore:
        """Evaluate the risk of a tool call with its specific arguments.

        Args:
            tool_name: The name of the tool being invoked.
            args: The arguments being passed to the tool.
            tool_risk: The static risk level assigned to the tool (1-5).

        Returns:
            RiskScore with evaluated risk level and reasoning.
        """
        ...


class PassthroughAnalyzer:
    """Stub analyzer that returns the tool's static risk level unchanged."""

    async def analyze(self, tool_name: str, args: dict, tool_risk: int) -> RiskScore:
        return RiskScore(level=tool_risk)


class PatternAnalyzer:
    """Argument-aware risk analysis using regex pattern matching.

    Scans tool arguments for patterns indicating risk — destructive commands,
    sensitive paths, privilege escalation, etc. Returns the highest matched
    risk level or falls back to the tool's static risk level.

    Can only escalate risk, never reduce it below the static tool_risk.

    Args:
        extra_patterns: Additional RiskPattern instances appended to the defaults.
        include_defaults: If False, only use extra_patterns (no built-in patterns).
    """

    def __init__(
        self,
        extra_patterns: list[RiskPattern] | None = None,
        include_defaults: bool = True,
    ) -> None:
        base = list(DEFAULT_PATTERNS) if include_defaults else []
        self._patterns = base + (extra_patterns or [])

    async def analyze(self, tool_name: str, args: dict, tool_risk: int) -> RiskScore:
        text = _flatten_args(args)
        if not text:
            return RiskScore(level=tool_risk)

        matches: list[RiskPattern] = []
        for p in self._patterns:
            if re.search(p.pattern, text, re.IGNORECASE):
                matches.append(p)

        if not matches:
            return RiskScore(level=tool_risk)

        worst = max(matches, key=lambda p: p.risk_level)
        assessed = max(tool_risk, worst.risk_level)
        reasons = [m.description for m in sorted(matches, key=lambda m: -m.risk_level)]

        return RiskScore(
            level=assessed,
            reasoning="; ".join(reasons),
        )


def _flatten_args(args: dict) -> str:
    """Flatten an args dict into a single string for pattern matching."""
    parts: list[str] = []
    for v in args.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(item) for item in v)
        else:
            parts.append(str(v))
    return " ".join(parts)
