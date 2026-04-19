"""Fire-and-forget event emitter for watch mode.

Wraps DatabaseService with typed emit methods. Exceptions are caught
and logged — emission must never block the watch cycle.
"""

import json
import logging
from typing import Any

from .database.service import DatabaseService


def _preview_for(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Build a compact effect preview for the approval UI.

    Returns a dict with a human-readable ``effect`` string plus the
    concrete ``command`` when the tool wraps a shell invocation. The
    preview is intentionally conservative — when effects are unknown we
    surface that rather than guess.
    """
    try:
        from .tools import get_tool_effect
    except Exception:
        effect = "mixed"
    else:
        try:
            effect = get_tool_effect(tool_name.split(":", 1)[0])
        except Exception:
            effect = "mixed"
    command = ""
    if isinstance(args, dict):
        for key in ("command", "cmd", "action", "name"):
            if key in args and args[key]:
                command = f"{key}={args[key]}"
                break
    return {"effect": effect, "command": command}


logger = logging.getLogger(__name__)


class WatchEventEmitter:
    """Typed event emitter backed by the watch_events table."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db
        self._watch_id: str | None = None
        self._watch_session_id: str | None = None

    def set_scope(self, *, watch_id: str, watch_session_id: str) -> None:
        """Set active watch/session identifiers for emitted events."""
        self._watch_id = watch_id
        self._watch_session_id = watch_session_id

    async def _emit(self, cycle: int, type: str, content: str | None = None, *, cycle_id: str | None = None) -> None:
        try:
            await self._db.insert_watch_event(
                cycle=cycle,
                type=type,
                content=content,
                watch_id=self._watch_id,
                watch_session_id=self._watch_session_id,
                cycle_id=cycle_id,
            )
        except Exception:
            logger.debug("Failed to emit watch event type=%s", type, exc_info=True)

    async def emit_cycle_start(self, cycle: int, session_id: str, *, cycle_id: str) -> None:
        await self._emit(
            cycle,
            "cycle_start",
            json.dumps({"session_id": session_id, "watch_session_id": self._watch_session_id, "cycle_id": cycle_id}),
            cycle_id=cycle_id,
        )

    async def emit_cycle_end(
        self,
        cycle: int,
        status: str,
        duration_seconds: float,
        tool_count: int,
        blocked_count: int = 0,
        outcome: dict | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cycle_id: str | None = None,
    ) -> None:
        await self._emit(
            cycle,
            "cycle_end",
            json.dumps(
                {
                    "status": status,
                    "duration_seconds": duration_seconds,
                    "tool_count": tool_count,
                    "blocked_count": blocked_count,
                    "outcome": outcome or {},
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
            ),
            cycle_id=cycle_id,
        )

    async def emit_token(self, cycle: int, content: str, *, cycle_id: str | None = None) -> None:
        await self._emit(cycle, "token", content, cycle_id=cycle_id)

    async def emit_tool_call(self, cycle: int, tool_name: str, args: dict, *, cycle_id: str | None = None) -> None:
        await self._emit(cycle, "tool_call", json.dumps({"name": tool_name, "args": args}), cycle_id=cycle_id)

    async def emit_tool_result(self, cycle: int, tool_name: str, output: str, *, cycle_id: str | None = None) -> None:
        await self._emit(
            cycle,
            "tool_result",
            json.dumps({"name": tool_name, "output": output[:500]}),
            cycle_id=cycle_id,
        )

    async def emit_approval_request(
        self,
        cycle: int,
        request_id: str,
        tool_name: str,
        args: dict,
        risk_level: int,
    ) -> None:
        preview = _preview_for(tool_name, args)
        await self._emit(
            cycle,
            "approval_request",
            json.dumps(
                {
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "args": args,
                    "risk_level": risk_level,
                    "preview": preview,
                }
            ),
        )

    async def emit_approval_resolved(self, cycle: int, request_id: str, status: str) -> None:
        await self._emit(cycle, "approval_resolved", json.dumps({"request_id": request_id, "status": status}))

    async def emit_approval_reminder(self, cycle: int, request_id: str, seconds_elapsed: int) -> None:
        await self._emit(
            cycle,
            "approval_reminder",
            json.dumps({"request_id": request_id, "seconds_elapsed": seconds_elapsed}),
        )

    async def emit_error(self, cycle: int, message: str, *, cycle_id: str | None = None) -> None:
        await self._emit(cycle, "error", json.dumps({"message": message}), cycle_id=cycle_id)

    async def emit_session_rotated(self, cycle: int, old_session_id: str, new_session_id: str) -> None:
        await self._emit(
            cycle,
            "session_rotated",
            json.dumps(
                {
                    "old_session_id": old_session_id,
                    "new_session_id": new_session_id,
                }
            ),
        )

    async def emit_phase(self, cycle: int, phase: str, summary: str, details: str | None = None) -> None:
        await self._emit(
            cycle,
            "phase",
            json.dumps(
                {
                    "phase": phase,
                    "summary": summary,
                    "details": details or "",
                }
            ),
        )

    async def emit_kill_switch(self, cycle: int, active: bool) -> None:
        await self._emit(
            cycle,
            "kill_switch",
            json.dumps({"active": bool(active)}),
        )

    async def emit_rate_limit(
        self,
        cycle: int,
        tool_name: str,
        count: int,
        ceiling: int,
    ) -> None:
        await self._emit(
            cycle,
            "rate_limit",
            json.dumps({"tool_name": tool_name, "count": count, "ceiling": ceiling}),
        )

    async def emit_incident(
        self,
        cycle: int,
        key: str,
        severity: str,
        title: str,
        detail: str,
        host: str,
        *,
        cycle_id: str | None = None,
    ) -> None:
        await self._emit(
            cycle,
            "incident",
            json.dumps(
                {
                    "key": key,
                    "severity": severity,
                    "title": title,
                    "detail": detail,
                    "host": host,
                }
            ),
            cycle_id=cycle_id,
        )
