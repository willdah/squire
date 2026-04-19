"""Reversible action registry for Phase 3 rollback.

Tools that can capture their pre-execution state and later restore it
register here. The watch controller consults this registry before
executing a matching tool to snapshot the prior state; the ``/incidents/
{key}/revert-last`` endpoint walks the snapshot back.

The registry is intentionally small — only high-confidence reversible
operations belong here. Destructive filesystem, package installs, and
network rule changes stay supervised rather than silently revertable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RevertOutcome:
    """Structured outcome of an attempted revert."""

    status: str  # "success" | "partial" | "failed" | "unavailable"
    evidence: str
    detail: dict[str, Any]


class RevertibleHandler:
    """Protocol-ish base for tool-level revert handlers.

    Subclasses implement ``capture`` (take a pre-state snapshot) and
    ``revert`` (apply the snapshot back).
    """

    async def capture(self, args: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def revert(self, args: dict[str, Any], pre_state: dict[str, Any]) -> RevertOutcome:  # pragma: no cover
        raise NotImplementedError


_REGISTRY: dict[str, RevertibleHandler] = {}


def register_revertible(tool_name: str, handler: RevertibleHandler) -> None:
    """Register a handler for a compound tool name (e.g. ``docker_container:restart``)."""
    _REGISTRY[tool_name] = handler


def get_revertible(tool_name: str) -> RevertibleHandler | None:
    return _REGISTRY.get(tool_name)


def is_revertible(tool_name: str) -> bool:
    return tool_name in _REGISTRY


def list_revertibles() -> list[str]:
    return sorted(_REGISTRY)
