"""ToolRegistry — Central registry for tool risk definitions.

Maps tool names to their static risk levels and metadata. Provides
the canonical source of truth for tool risk when integrated with
RiskEvaluator.
Framework-agnostic — no imports from squire or any agent framework.
"""

from .models import ToolDef


class ToolRegistry:
    """Registry mapping tool names to risk levels and metadata.

    Args:
        default_risk: Risk level for tools not explicitly registered (1-5).
            Defaults to 5 (highest) — unknown tools are treated as dangerous.
    """

    def __init__(self, default_risk: int = 5) -> None:
        self._tools: dict[str, ToolDef] = {}
        self.default_risk = default_risk

    def register(
        self,
        name: str,
        risk: int,
        *,
        description: str = "",
        tags: frozenset[str] | None = None,
    ) -> ToolDef:
        """Register a tool with its risk level.

        Args:
            name: The tool name (must be unique).
            risk: Static risk level (1-5).
            description: Human-readable description of what the tool does.
            tags: Optional tags for categorization.

        Returns:
            The created ToolDef.
        """
        tool = ToolDef(
            name=name,
            risk=risk,
            description=description,
            tags=tags or frozenset(),
        )
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> ToolDef | None:
        """Get a tool definition by name, or None if not registered."""
        return self._tools.get(name)

    def get_risk(self, name: str) -> int:
        """Get risk level for a tool, falling back to default_risk if unknown."""
        tool = self._tools.get(name)
        return tool.risk if tool else self.default_risk

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
