"""Tests for the alert-rule notification tools.

Covers the structured ``field`` / ``op`` / ``value`` argument refactor
introduced alongside the prompting review punch-list: the happy path,
the "change the condition? pass all three" guard, the ``_format_value``
helper, and partial updates.
"""

import sqlite3
from unittest.mock import AsyncMock

import pytest

from squire.tools._registry import set_db
from squire.tools.notifications.create_alert_rule import _format_value, create_alert_rule
from squire.tools.notifications.update_alert_rule import update_alert_rule


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.save_alert_rule = AsyncMock(return_value=42)
    db.update_alert_rule = AsyncMock(return_value=True)
    set_db(db)
    yield db
    set_db(None)


class TestFormatValue:
    def test_integer_valued_float_renders_without_decimal(self):
        assert _format_value(90.0) == "90"

    def test_non_integer_float_preserves_decimal(self):
        assert _format_value(85.5) == "85.5"

    def test_int_input(self):
        assert _format_value(90) == "90"


class TestCreateAlertRule:
    @pytest.mark.asyncio
    async def test_happy_path_builds_condition_string(self, mock_db):
        result = await create_alert_rule(
            name="cpu-high",
            field="cpu_percent",
            op=">",
            value=90.0,
        )
        mock_db.save_alert_rule.assert_awaited_once()
        kwargs = mock_db.save_alert_rule.await_args.kwargs
        assert kwargs["name"] == "cpu-high"
        assert kwargs["condition"] == "cpu_percent > 90"
        assert kwargs["host"] == "all"
        assert kwargs["severity"] == "warning"
        assert "created" in result
        assert "cpu-high" in result

    @pytest.mark.asyncio
    async def test_preserves_fractional_threshold(self, mock_db):
        await create_alert_rule(name="cpu-half", field="cpu_percent", op=">=", value=85.5)
        kwargs = mock_db.save_alert_rule.await_args.kwargs
        assert kwargs["condition"] == "cpu_percent >= 85.5"

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_error_string(self, mock_db):
        mock_db.save_alert_rule.side_effect = sqlite3.IntegrityError("UNIQUE constraint failed")
        result = await create_alert_rule(name="dup", field="cpu_percent", op=">", value=90)
        assert result.startswith("Error:")
        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_missing_db_returns_error_string(self):
        set_db(None)
        result = await create_alert_rule(name="x", field="cpu_percent", op=">", value=90)
        assert result.startswith("Error:")
        assert "database not configured" in result


class TestUpdateAlertRule:
    @pytest.mark.asyncio
    async def test_partial_condition_rejected(self, mock_db):
        result = await update_alert_rule(name="cpu-high", field="cpu_percent")
        assert result.startswith("Error:")
        assert "field, op, and value" in result
        mock_db.update_alert_rule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_all_three_changes_condition(self, mock_db):
        result = await update_alert_rule(
            name="cpu-high",
            field="cpu_percent",
            op=">",
            value=85,
        )
        mock_db.update_alert_rule.assert_awaited_once()
        kwargs = mock_db.update_alert_rule.await_args.kwargs
        assert kwargs["condition"] == "cpu_percent > 85"
        assert "Updated" in result

    @pytest.mark.asyncio
    async def test_no_condition_change_still_updates_other_fields(self, mock_db):
        result = await update_alert_rule(name="cpu-high", severity="critical", enabled=False)
        kwargs = mock_db.update_alert_rule.await_args.kwargs
        assert "condition" not in kwargs
        assert kwargs["severity"] == "critical"
        assert kwargs["enabled"] is False
        assert "Updated" in result

    @pytest.mark.asyncio
    async def test_no_fields_returns_error(self, mock_db):
        result = await update_alert_rule(name="cpu-high")
        assert result.startswith("Error:")
        assert "no fields" in result
        mock_db.update_alert_rule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_rule_returns_error(self, mock_db):
        mock_db.update_alert_rule.return_value = False
        result = await update_alert_rule(name="ghost", severity="info")
        assert result.startswith("Error:")
        assert "not found" in result
