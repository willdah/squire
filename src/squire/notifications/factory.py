"""Build NotificationRouter from NotificationsConfig (shared by web lifespan and config PATCH)."""

from __future__ import annotations

from typing import Any

from ..config.notifications import NotificationsConfig
from .email import EmailNotifier
from .router import NotificationRouter
from .webhook import WebhookDispatcher


def build_notification_router(cfg: NotificationsConfig, db: Any | None = None) -> NotificationRouter:
    """Create webhook + optional email channels wrapped in NotificationRouter."""
    webhook = WebhookDispatcher(cfg)
    email_notifier = None
    if cfg.email and cfg.email.enabled:
        email_notifier = EmailNotifier(cfg.email)
    return NotificationRouter(webhook=webhook, email=email_notifier, db=db)
