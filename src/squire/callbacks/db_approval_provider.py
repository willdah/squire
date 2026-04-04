"""SQLite-backed approval provider for watch mode.

Bridges tool approval requests through the database so the web UI
can approve/deny tools while watch runs as a separate process.
"""

import asyncio
import json
import logging
import uuid

from ..database.service import DatabaseService
from ..watch_emitter import WatchEventEmitter

logger = logging.getLogger(__name__)


class DatabaseApprovalProvider:
    """Approval provider that writes requests to SQLite and polls for responses.

    Satisfies the AsyncApprovalProvider protocol.
    """

    def __init__(
        self,
        db: DatabaseService,
        emitter: WatchEventEmitter,
        cycle: int,
        timeout: float = 60.0,
        poll_interval: float = 0.2,
    ) -> None:
        self._db = db
        self._emitter = emitter
        self.cycle = cycle
        self._timeout = timeout
        self._poll_interval = poll_interval

    async def request_approval_async(
        self,
        tool_name: str,
        args: dict,
        risk_level: int,
    ) -> bool:
        """Request approval via database, polling until resolved or timeout."""
        request_id = str(uuid.uuid4())

        await self._emitter.emit_approval_request(
            cycle=self.cycle,
            request_id=request_id,
            tool_name=tool_name,
            args=args,
            risk_level=risk_level,
        )
        await self._db.insert_watch_approval(
            request_id=request_id,
            tool_name=tool_name,
            args=json.dumps(args),
            risk_level=risk_level,
        )

        elapsed = 0.0
        while elapsed < self._timeout:
            await asyncio.sleep(self._poll_interval)
            elapsed += self._poll_interval

            approval = await self._db.get_watch_approval(request_id)
            if approval and approval["status"] != "pending":
                approved = approval["status"] == "approved"
                await self._emitter.emit_approval_resolved(
                    self.cycle,
                    request_id,
                    approval["status"],
                )
                return approved

        await self._db.update_watch_approval(request_id, "expired")
        await self._emitter.emit_approval_resolved(self.cycle, request_id, "expired")
        logger.info("Approval for '%s' timed out after %.0fs", tool_name, self._timeout)
        return False
