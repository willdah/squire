"""Async webhook dispatcher for Renew notifications.

Sends event payloads to configured webhook endpoints via httpx.
Each webhook can filter which event categories it receives.
"""

import logging
from datetime import UTC, datetime

import httpx

from ..config.notifications import NotificationsConfig, WebhookConfig

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatches event notifications to configured webhook endpoints."""

    def __init__(self, config: NotificationsConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def _matches(self, webhook: WebhookConfig, category: str) -> bool:
        """Check if a webhook is subscribed to this event category."""
        return "*" in webhook.events or category in webhook.events

    async def dispatch(
        self,
        *,
        category: str,
        summary: str,
        details: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Send an event to all matching webhooks.

        Failures are logged but never raised — notifications must not
        break the main application flow.
        """
        if not self._config.enabled or not self._config.webhooks:
            return

        payload = {
            "app": "renew",
            "timestamp": datetime.now(UTC).isoformat(),
            "category": category,
            "summary": summary,
        }
        if details:
            payload["details"] = details
        if session_id:
            payload["session_id"] = session_id
        if tool_name:
            payload["tool_name"] = tool_name

        client = await self._get_client()

        for webhook in self._config.webhooks:
            if not self._matches(webhook, category):
                continue
            try:
                resp = await client.post(
                    webhook.url,
                    json=payload,
                    headers=webhook.headers,
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Webhook '%s' returned %d: %s",
                        webhook.name,
                        resp.status_code,
                        resp.text[:200],
                    )
            except Exception:
                logger.warning("Webhook '%s' failed", webhook.name, exc_info=True)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
