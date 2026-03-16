"""Tests for the background alert evaluator."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from squire.notifications.alert_evaluator import evaluate_alerts


def _make_rule(
    name="test-rule",
    condition="cpu_percent > 90",
    host="all",
    severity="warning",
    cooldown_minutes=30,
    enabled=1,
    last_fired_at=None,
):
    return {
        "name": name,
        "condition": condition,
        "host": host,
        "severity": severity,
        "cooldown_minutes": cooldown_minutes,
        "enabled": enabled,
        "last_fired_at": last_fired_at,
    }


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_active_alert_rules = AsyncMock(return_value=[])
    db.update_alert_last_fired = AsyncMock()
    return db


@pytest.fixture
def mock_notifier():
    return AsyncMock()


class TestAlertEvaluation:
    @pytest.mark.asyncio
    async def test_no_rules_returns_zero(self, mock_db, mock_notifier):
        fired = await evaluate_alerts(mock_db, mock_notifier, {"local": {"cpu_percent": 95}})
        assert fired == 0

    @pytest.mark.asyncio
    async def test_fires_when_condition_met(self, mock_db, mock_notifier):
        mock_db.get_active_alert_rules.return_value = [_make_rule()]
        snapshot = {"local": {"cpu_percent": 95}}
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 1
        mock_notifier.dispatch.assert_called_once()
        mock_db.update_alert_last_fired.assert_called_once_with("test-rule")

    @pytest.mark.asyncio
    async def test_does_not_fire_when_condition_not_met(self, mock_db, mock_notifier):
        mock_db.get_active_alert_rules.return_value = [_make_rule()]
        snapshot = {"local": {"cpu_percent": 50}}
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 0
        mock_notifier.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_cooldown(self, mock_db, mock_notifier):
        recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        mock_db.get_active_alert_rules.return_value = [_make_rule(cooldown_minutes=30, last_fired_at=recent)]
        snapshot = {"local": {"cpu_percent": 95}}
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 0

    @pytest.mark.asyncio
    async def test_fires_after_cooldown_expires(self, mock_db, mock_notifier):
        old = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
        mock_db.get_active_alert_rules.return_value = [_make_rule(cooldown_minutes=30, last_fired_at=old)]
        snapshot = {"local": {"cpu_percent": 95}}
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 1

    @pytest.mark.asyncio
    async def test_host_specific_rule(self, mock_db, mock_notifier):
        mock_db.get_active_alert_rules.return_value = [_make_rule(host="media-server")]
        snapshot = {
            "local": {"cpu_percent": 95},
            "media-server": {"cpu_percent": 50},
        }
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 0  # media-server cpu is only 50

    @pytest.mark.asyncio
    async def test_host_all_checks_all_hosts(self, mock_db, mock_notifier):
        mock_db.get_active_alert_rules.return_value = [_make_rule(host="all")]
        snapshot = {
            "local": {"cpu_percent": 50},
            "media-server": {"cpu_percent": 95},
        }
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 1

    @pytest.mark.asyncio
    async def test_skips_invalid_condition(self, mock_db, mock_notifier):
        mock_db.get_active_alert_rules.return_value = [_make_rule(condition="not valid")]
        snapshot = {"local": {"cpu_percent": 95}}
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 0

    @pytest.mark.asyncio
    async def test_skips_unreachable_hosts(self, mock_db, mock_notifier):
        mock_db.get_active_alert_rules.return_value = [_make_rule(host="all")]
        snapshot = {
            "local": {"cpu_percent": 50},
            "broken": {"error": "unreachable"},
        }
        fired = await evaluate_alerts(mock_db, mock_notifier, snapshot)
        assert fired == 0
