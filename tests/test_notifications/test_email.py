"""Tests for the email notifier."""

from unittest.mock import MagicMock, patch

import pytest

from squire.config.notifications import EmailConfig
from squire.notifications.email import EmailNotifier


@pytest.fixture
def email_config():
    return EmailConfig(
        enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        use_tls=True,
        smtp_user="user@example.com",
        smtp_password="secret",
        from_address="squire@example.com",
        to_addresses=["admin@example.com"],
        events=["*"],
    )


class TestEmailNotifier:
    @pytest.mark.asyncio
    async def test_dispatch_sends_email(self, email_config):
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            await notifier.dispatch(category="watch.alert", summary="CPU high")
            mock_server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_matching_events(self, email_config):
        email_config.events = ["error"]
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            await notifier.dispatch(category="watch.alert", summary="CPU high")
            mock_smtp.SMTP.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_disabled_is_noop(self, email_config):
        email_config.enabled = False
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            await notifier.dispatch(category="watch.alert", summary="CPU high")
            mock_smtp.SMTP.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_no_recipients_is_noop(self, email_config):
        email_config.to_addresses = []
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            await notifier.dispatch(category="watch.alert", summary="test")
            mock_smtp.SMTP.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_error_does_not_raise(self, email_config):
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            mock_smtp.SMTP.side_effect = ConnectionRefusedError("SMTP down")
            await notifier.dispatch(category="watch.alert", summary="test")
            # Should not raise

    @pytest.mark.asyncio
    async def test_wildcard_matches_all_events(self, email_config):
        email_config.events = ["*"]
        notifier = EmailNotifier(email_config)
        assert notifier._matches("watch.alert")
        assert notifier._matches("error")
        assert notifier._matches("anything")

    @pytest.mark.asyncio
    async def test_specific_event_filter(self, email_config):
        email_config.events = ["watch.alert", "error"]
        notifier = EmailNotifier(email_config)
        assert notifier._matches("watch.alert")
        assert notifier._matches("error")
        assert not notifier._matches("watch.start")
