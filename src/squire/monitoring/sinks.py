"""Per-session delivery of monitor results (Web UI, TUI, watch)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from fastapi import WebSocket

if TYPE_CHECKING:
    from ..database.service import DatabaseService

logger = logging.getLogger(__name__)

_SESSION_SINKS: dict[str, MonitorSessionSink] = {}


class MonitorSessionSink(Protocol):
    """Delivers monitor completion to the right channel for this session."""

    use_background: bool

    async def deliver_monitor_result(self, monitor_id: str, content: str) -> None:
        """Persist and notify the user that a monitor finished."""


def register_monitor_session_sink(session_id: str, sink: MonitorSessionSink) -> None:
    _SESSION_SINKS[session_id] = sink


def unregister_monitor_session_sink(session_id: str) -> None:
    _SESSION_SINKS.pop(session_id, None)


def get_monitor_session_sink(session_id: str) -> MonitorSessionSink | None:
    return _SESSION_SINKS.get(session_id)


@dataclass
class WebChatMonitorSink:
    """Inject assistant text over the chat WebSocket (Option B)."""

    websocket: WebSocket
    db: DatabaseService | None
    session_id: str
    use_background: bool = True
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def deliver_monitor_result(self, monitor_id: str, content: str) -> None:
        from starlette.websockets import WebSocketState

        async with self._send_lock:
            if self.db:
                try:
                    await self.db.save_message(session_id=self.session_id, role="assistant", content=content)
                    await self.db.update_session_active(self.session_id)
                    await self.db.log_event(
                        category="monitor",
                        summary=f"Monitor {monitor_id} completed",
                        session_id=self.session_id,
                        tool_name="wait_for_state",
                        details=content[:2000],
                    )
                except Exception:
                    logger.debug("Failed to persist monitor result", exc_info=True)
            if self.websocket.client_state != WebSocketState.CONNECTED:
                return
            try:
                await self.websocket.send_json(
                    {
                        "type": "monitor_complete",
                        "content": content,
                        "monitor_id": monitor_id,
                    }
                )
            except Exception:
                logger.debug("WebSocket send failed for monitor_complete", exc_info=True)


@dataclass
class TuiChatMonitorSink:
    """Append a monitor result bubble in the Textual chat (main thread)."""

    db: DatabaseService | None
    notifier: object | None
    session_id: str
    app: object
    add_message: object
    use_background: bool = True

    async def deliver_monitor_result(self, monitor_id: str, content: str) -> None:
        if self.db:
            try:
                await self.db.save_message(session_id=self.session_id, role="assistant", content=content)
                await self.db.update_session_active(self.session_id)
                await self.db.log_event(
                    category="monitor",
                    summary=f"Monitor {monitor_id} completed",
                    session_id=self.session_id,
                    tool_name="wait_for_state",
                    details=content[:2000],
                )
            except Exception:
                logger.debug("Failed to persist monitor result (TUI)", exc_info=True)
        if self.notifier:
            try:
                await self.notifier.dispatch(
                    category="monitor",
                    summary=f"Monitor {monitor_id} completed",
                    session_id=self.session_id,
                    tool_name="wait_for_state",
                    details=content[:500],
                )
            except Exception:
                logger.debug("Notifier dispatch failed for monitor", exc_info=True)
        self.app.call_from_thread(self.add_message, content, "assistant")


@dataclass
class WatchNotifierMonitorSink:
    """Watch mode: log and notify; no UI injection."""

    db: DatabaseService | None
    notifier: object | None
    session_id: str
    use_background: bool = True

    async def deliver_monitor_result(self, monitor_id: str, content: str) -> None:
        if self.db:
            try:
                await self.db.save_message(session_id=self.session_id, role="assistant", content=content)
                await self.db.update_session_active(self.session_id)
                await self.db.log_event(
                    category="monitor",
                    summary=f"Monitor {monitor_id} completed",
                    session_id=self.session_id,
                    tool_name="wait_for_state",
                    details=content[:2000],
                )
            except Exception:
                logger.debug("Failed to persist monitor result (watch)", exc_info=True)
        if self.notifier:
            try:
                await self.notifier.dispatch(
                    category="monitor",
                    summary=f"[Watch] {content[:200]}",
                    session_id=self.session_id,
                    tool_name="wait_for_state",
                    details=content[:2000],
                )
            except Exception:
                logger.debug("Notifier dispatch failed for watch monitor", exc_info=True)
