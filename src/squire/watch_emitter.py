"""Fire-and-forget event emitter for watch mode.

Wraps DatabaseService with typed emit methods. Exceptions are caught
and logged — emission must never block the watch cycle.
"""

import json
import logging

from .database.service import DatabaseService

logger = logging.getLogger(__name__)


class WatchEventEmitter:
    """Typed event emitter backed by the watch_events table."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def _emit(self, cycle: int, type: str, content: str | None = None) -> None:
        try:
            await self._db.insert_watch_event(cycle=cycle, type=type, content=content)
        except Exception:
            logger.debug("Failed to emit watch event type=%s", type, exc_info=True)

    async def emit_cycle_start(self, cycle: int, session_id: str) -> None:
        await self._emit(cycle, "cycle_start", json.dumps({"session_id": session_id}))

    async def emit_cycle_end(self, cycle: int, status: str, duration_seconds: float, tool_count: int) -> None:
        await self._emit(cycle, "cycle_end", json.dumps({
            "status": status, "duration_seconds": duration_seconds, "tool_count": tool_count,
        }))

    async def emit_token(self, cycle: int, content: str) -> None:
        await self._emit(cycle, "token", content)

    async def emit_tool_call(self, cycle: int, tool_name: str, args: dict) -> None:
        await self._emit(cycle, "tool_call", json.dumps({"name": tool_name, "args": args}))

    async def emit_tool_result(self, cycle: int, tool_name: str, output: str) -> None:
        await self._emit(cycle, "tool_result", json.dumps({"name": tool_name, "output": output[:500]}))

    async def emit_approval_request(self, cycle: int, request_id: str, tool_name: str, args: dict, risk_level: int) -> None:
        await self._emit(cycle, "approval_request", json.dumps({
            "request_id": request_id, "tool_name": tool_name, "args": args, "risk_level": risk_level,
        }))

    async def emit_approval_resolved(self, cycle: int, request_id: str, status: str) -> None:
        await self._emit(cycle, "approval_resolved", json.dumps({"request_id": request_id, "status": status}))

    async def emit_error(self, cycle: int, message: str) -> None:
        await self._emit(cycle, "error", json.dumps({"message": message}))

    async def emit_session_rotated(self, cycle: int, old_session_id: str, new_session_id: str) -> None:
        await self._emit(cycle, "session_rotated", json.dumps({
            "old_session_id": old_session_id, "new_session_id": new_session_id,
        }))
