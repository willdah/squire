"""Tool-level backend registry accessor.

Separated from __init__.py to avoid circular imports — tool modules
import from here, and __init__.py imports tool modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..system.registry import BackendRegistry

_registry: BackendRegistry | None = None


def set_registry(registry: BackendRegistry | None) -> None:
    """Set the global backend registry (called at startup)."""
    global _registry
    _registry = registry


def get_registry():
    """Return the global backend registry.

    Falls back to a default registry with only the local backend
    if none has been set (e.g. during tests or standalone usage).
    """
    if _registry is None:
        from ..system.registry import BackendRegistry

        return BackendRegistry()
    return _registry
