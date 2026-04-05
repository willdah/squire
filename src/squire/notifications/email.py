"""Email notification channel using stdlib smtplib."""

import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from email.mime.text import MIMEText

from ..config.notifications import EmailConfig

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send notifications via SMTP email.

    SMTP operations run in an executor to avoid blocking the event loop.
    Failures are logged but never raised.
    """

    def __init__(self, config: EmailConfig) -> None:
        self._config = config

    def _matches(self, category: str) -> bool:
        """Check if a category matches the configured event filter."""
        return "*" in self._config.events or category in self._config.events

    async def dispatch(
        self,
        *,
        category: str,
        summary: str,
        details: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Send an email notification to configured recipients."""
        if not self._config.enabled or not self._config.to_addresses:
            return
        if not self._matches(category):
            return

        subject = f"[Squire] [{category}] {summary}"
        body_parts = [
            f"Category: {category}",
            f"Time: {datetime.now(UTC).isoformat()}",
            f"Summary: {summary}",
        ]
        if details:
            body_parts.append(f"\nDetails:\n{details}")
        if session_id:
            body_parts.append(f"Session: {session_id}")
        if tool_name:
            body_parts.append(f"Tool: {tool_name}")

        body = "\n".join(body_parts)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._send_sync, subject, body)
        except Exception:
            logger.warning("Failed to send email notification", exc_info=True)

    def _send_sync(self, subject: str, body: str) -> None:
        """Blocking SMTP send — called from executor."""
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._config.from_address
        msg["To"] = ", ".join(self._config.to_addresses)

        with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as server:
            if self._config.use_tls:
                server.starttls()
            if self._config.smtp_user and self._config.smtp_password:
                server.login(self._config.smtp_user, self._config.smtp_password)
            server.send_message(msg)

    async def close(self) -> None:
        """No persistent connection to clean up."""
