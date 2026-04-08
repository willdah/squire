"""Track and cancel background monitor tasks per chat session."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# session_id -> list of asyncio Tasks
_session_tasks: dict[str, list[asyncio.Task]] = {}


def _prune_task(session_id: str, task: asyncio.Task) -> None:
    lst = _session_tasks.get(session_id)
    if not lst:
        return
    try:
        lst.remove(task)
    except ValueError:
        pass
    if not lst:
        _session_tasks.pop(session_id, None)


def track_monitor_task(session_id: str, task: asyncio.Task) -> None:
    """Register a background monitor task so it can be cancelled on disconnect."""

    def _done(t: asyncio.Task) -> None:
        _prune_task(session_id, t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.debug("Monitor task ended with error", exc_info=exc)

    _session_tasks.setdefault(session_id, []).append(task)
    task.add_done_callback(_done)


def cancel_session_monitor_tasks(session_id: str) -> None:
    """Cancel all monitor tasks for a session (e.g. WebSocket disconnect)."""
    tasks = _session_tasks.pop(session_id, [])
    for t in tasks:
        if not t.done():
            t.cancel()
