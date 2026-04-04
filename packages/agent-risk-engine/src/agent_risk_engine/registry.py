"""ActionRegistry — Central registry for action risk definitions.

Maps action names to their static risk levels and metadata. Provides
the canonical source of truth for action risk when integrated with
RiskEvaluator.
Framework-agnostic — no external dependencies.
"""

from .models import ActionDef


class ActionRegistry:
    """Registry mapping action names to risk levels and metadata.

    Args:
        default_risk: Risk level for actions not explicitly registered (1-5).
            Defaults to 5 (highest) — unknown actions are treated as dangerous.
    """

    def __init__(self, default_risk: int = 5) -> None:
        self._actions: dict[str, ActionDef] = {}
        self.default_risk = default_risk

    def register(
        self,
        name: str,
        kind: str,
        risk: int,
        *,
        description: str = "",
        tags: frozenset[str] | None = None,
    ) -> ActionDef:
        """Register an action with its risk level.

        Args:
            name: The action name (must be unique).
            kind: Action category (e.g., "tool_call", "file_write").
            risk: Static risk level (1-5).
            description: Human-readable description.
            tags: Optional tags for categorization.

        Returns:
            The created ActionDef.
        """
        action = ActionDef(
            name=name,
            kind=kind,
            risk=risk,
            description=description,
            tags=tags or frozenset(),
        )
        self._actions[name] = action
        return action

    def get(self, name: str) -> ActionDef | None:
        """Get an action definition by name, or None if not registered."""
        return self._actions.get(name)

    def get_risk(self, name: str) -> int:
        """Get risk level for an action, falling back to default_risk if unknown."""
        action = self._actions.get(name)
        return action.risk if action else self.default_risk

    def __contains__(self, name: str) -> bool:
        return name in self._actions

    def __len__(self) -> int:
        return len(self._actions)
