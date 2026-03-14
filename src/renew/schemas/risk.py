from enum import StrEnum

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """Risk level assigned to each tool."""

    READ = "read"
    CAUTIOUS = "cautious"
    STANDARD = "standard"
    FULL = "full"


class GateResult(StrEnum):
    """Outcome of a risk profile evaluation."""

    ALLOWED = "allowed"
    NEEDS_APPROVAL = "needs_approval"
    DENIED = "denied"


# Defines which risk levels are auto-allowed for each built-in profile.
# Anything not auto-allowed requires approval, except read-only which denies non-read.
_PROFILE_ALLOWED_LEVELS: dict[str, set[RiskLevel]] = {
    "read-only": {RiskLevel.READ},
    "cautious": {RiskLevel.READ, RiskLevel.CAUTIOUS},
    "standard": {RiskLevel.READ, RiskLevel.CAUTIOUS, RiskLevel.STANDARD},
    "full-trust": {RiskLevel.READ, RiskLevel.CAUTIOUS, RiskLevel.STANDARD, RiskLevel.FULL},
}


class RiskProfile(BaseModel):
    """Determines what tools are allowed, need approval, or are denied."""

    name: str = "cautious"

    # Only used when name == "custom"
    allowed_tools: set[str] = Field(default_factory=set)
    approval_tools: set[str] = Field(default_factory=set)
    denied_tools: set[str] = Field(default_factory=set)

    def gate(self, tool_name: str, risk_level: str) -> GateResult:
        """Evaluate whether a tool call should be allowed, need approval, or be denied."""
        if self.name == "custom":
            return self._gate_custom(tool_name)
        return self._gate_builtin(tool_name, RiskLevel(risk_level))

    def _gate_builtin(self, tool_name: str, risk_level: RiskLevel) -> GateResult:
        allowed_levels = _PROFILE_ALLOWED_LEVELS.get(self.name, set())
        if risk_level in allowed_levels:
            return GateResult.ALLOWED

        # read-only denies everything that isn't read-level
        if self.name == "read-only":
            return GateResult.DENIED

        # Other profiles require approval for higher risk levels
        return GateResult.NEEDS_APPROVAL

    def _gate_custom(self, tool_name: str) -> GateResult:
        if tool_name in self.denied_tools:
            return GateResult.DENIED
        if tool_name in self.allowed_tools:
            return GateResult.ALLOWED
        if tool_name in self.approval_tools:
            return GateResult.NEEDS_APPROVAL
        # Default: require approval for unlisted tools
        return GateResult.NEEDS_APPROVAL
