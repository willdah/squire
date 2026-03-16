"""Tool-level service registry — provides access to shared dependencies.

Separated from __init__.py to avoid circular imports — tool modules
import from here, and __init__.py imports tool modules.

Provides accessors for:
- BackendRegistry (local/SSH backends for command execution)
- DatabaseService (persistence for sessions, events, alert rules)
- WebhookDispatcher (notification delivery)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..database.service import DatabaseService
    from ..notifications.webhook import WebhookDispatcher
    from ..system.registry import BackendRegistry

_registry: BackendRegistry | None = None
_db: DatabaseService | None = None
_notifier: WebhookDispatcher | None = None


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


def set_db(db: DatabaseService | None) -> None:
    """Set the global database service (called at startup)."""
    global _db
    _db = db


def get_db():
    """Return the global database service.

    Returns None if not set — callers should handle gracefully.
    """
    return _db


def set_notifier(notifier: WebhookDispatcher | None) -> None:
    """Set the global webhook dispatcher (called at startup)."""
    global _notifier
    _notifier = notifier


def get_notifier():
    """Return the global webhook dispatcher.

    Returns None if not set — callers should handle gracefully.
    """
    return _notifier
