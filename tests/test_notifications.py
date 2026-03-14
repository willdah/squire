"""Tests for webhook notification dispatcher."""

import pytest

from squire.config.notifications import NotificationsConfig, WebhookConfig
from squire.notifications.webhook import WebhookDispatcher


@pytest.mark.asyncio
async def test_disabled_is_noop():
    d = WebhookDispatcher(NotificationsConfig(enabled=False))
    await d.dispatch(category="error", summary="test")
    # No exception, no HTTP call


@pytest.mark.asyncio
async def test_wildcard_matches_all():
    wh = WebhookConfig(name="all", url="http://localhost:1", events=["*"])
    d = WebhookDispatcher(NotificationsConfig(enabled=True, webhooks=[wh]))
    assert d._matches(wh, "tool_call")
    assert d._matches(wh, "error")
    assert d._matches(wh, "anything")


@pytest.mark.asyncio
async def test_specific_event_filter():
    wh = WebhookConfig(name="errors", url="http://localhost:1", events=["error"])
    d = WebhookDispatcher(NotificationsConfig(enabled=True, webhooks=[wh]))
    assert d._matches(wh, "error")
    assert not d._matches(wh, "tool_call")


@pytest.mark.asyncio
async def test_unreachable_webhook_does_not_raise():
    config = NotificationsConfig(
        enabled=True,
        webhooks=[WebhookConfig(name="broken", url="http://localhost:1/nope", events=["*"])],
    )
    d = WebhookDispatcher(config)
    await d.dispatch(category="error", summary="should not raise")
    await d.close()
