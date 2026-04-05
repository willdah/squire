"""Tests for the notification router."""

from unittest.mock import AsyncMock

import pytest

from squire.notifications.router import NotificationRouter


@pytest.fixture
def mock_webhook():
    return AsyncMock()


@pytest.fixture
def mock_email():
    return AsyncMock()


class TestNotificationRouter:
    @pytest.mark.asyncio
    async def test_dispatches_to_webhook(self, mock_webhook):
        router = NotificationRouter(webhook=mock_webhook)
        await router.dispatch(category="test", summary="hello")
        mock_webhook.dispatch.assert_called_once_with(
            category="test",
            summary="hello",
            details=None,
            session_id=None,
            tool_name=None,
        )

    @pytest.mark.asyncio
    async def test_dispatches_to_email(self, mock_webhook, mock_email):
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.dispatch(category="test", summary="hello")
        mock_email.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_email_is_fine(self, mock_webhook):
        router = NotificationRouter(webhook=mock_webhook)
        await router.dispatch(category="test", summary="hello")
        # No error, only webhook called

    @pytest.mark.asyncio
    async def test_webhook_error_does_not_block_email(self, mock_webhook, mock_email):
        mock_webhook.dispatch.side_effect = Exception("webhook down")
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.dispatch(category="test", summary="hello")
        mock_email.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_error_does_not_block(self, mock_webhook, mock_email):
        mock_email.dispatch.side_effect = Exception("smtp down")
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.dispatch(category="test", summary="hello")
        mock_webhook.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_delegates(self, mock_webhook, mock_email):
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.close()
        mock_webhook.close.assert_called_once()
        mock_email.close.assert_called_once()
