"""Notification router — dispatches to all configured channels."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotificationRouter:
    """Routes notifications to webhook and email channels.

    Drop-in replacement for WebhookDispatcher — same ``dispatch()`` interface.
    Failures in one channel do not block others.
    """

    def __init__(self, webhook: Any, email: Any | None = None) -> None:
        self._webhook = webhook
        self._email = email

    async def dispatch(
        self,
        *,
        category: str,
        summary: str,
        details: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Send to all configured channels. Failures are logged, never raised."""
        kwargs = dict(category=category, summary=summary, details=details, session_id=session_id, tool_name=tool_name)

        try:
            await self._webhook.dispatch(**kwargs)
        except Exception:
            logger.warning("Webhook dispatch failed", exc_info=True)

        if self._email is not None:
            try:
                await self._email.dispatch(**kwargs)
            except Exception:
                logger.warning("Email dispatch failed", exc_info=True)

    async def close(self) -> None:
        """Clean up all channel resources."""
        await self._webhook.close()
        if self._email is not None:
            await self._email.close()
