"""Tests for DatabaseOverrideSource — pydantic-settings source backed by SQLite."""

import json

import pytest

import squire.config.loader as loader_mod
from squire.config import GuardrailsConfig, WatchConfig
from squire.config.db_source import DatabaseOverrideSource


@pytest.fixture(autouse=True)
def _empty_toml(monkeypatch):
    monkeypatch.setattr(loader_mod, "_cached", {})


@pytest.mark.asyncio
async def test_db_overrides_apply_to_watch_config(db, monkeypatch):
    monkeypatch.setenv("SQUIRE_DB_PATH", str(db._db_path))
    await db.set_config_section_overrides("watch", {"interval_minutes": 42})

    config = WatchConfig()
    assert config.interval_minutes == 42


@pytest.mark.asyncio
async def test_env_precedence_over_db(db, monkeypatch):
    monkeypatch.setenv("SQUIRE_DB_PATH", str(db._db_path))
    monkeypatch.setenv("SQUIRE_WATCH_INTERVAL_MINUTES", "11")
    await db.set_config_section_overrides("watch", {"interval_minutes": 99})

    config = WatchConfig()
    assert config.interval_minutes == 11  # env wins


@pytest.mark.asyncio
async def test_missing_db_returns_defaults(tmp_path, monkeypatch):
    # Point at a non-existent DB path.
    monkeypatch.setenv("SQUIRE_DB_PATH", str(tmp_path / "does-not-exist.db"))
    config = WatchConfig()
    assert config.interval_minutes == 5  # code default


@pytest.mark.asyncio
async def test_pre_schema_db_returns_defaults(tmp_path, monkeypatch):
    # Create an empty SQLite file with no schema.
    import sqlite3

    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.close()
    monkeypatch.setenv("SQUIRE_DB_PATH", str(db_path))

    config = WatchConfig()
    assert config.interval_minutes == 5


@pytest.mark.asyncio
async def test_override_source_returns_empty_for_other_sections(db, monkeypatch):
    monkeypatch.setenv("SQUIRE_DB_PATH", str(db._db_path))
    await db.set_config_section_overrides("watch", {"interval_minutes": 2})

    # A different section's source must NOT pick up watch's overrides.
    source = DatabaseOverrideSource(GuardrailsConfig, "guardrails")
    assert source() == {}


@pytest.mark.asyncio
async def test_override_source_filters_unknown_fields(db, monkeypatch):
    monkeypatch.setenv("SQUIRE_DB_PATH", str(db._db_path))
    # Write a row for a field WatchConfig does not define — should be ignored.
    conn = await db._get_conn()
    await conn.execute(
        "INSERT INTO config_overrides (section, field, value_json, updated_at) VALUES (?, ?, ?, ?)",
        ("watch", "not_a_field", json.dumps("ignored"), "now"),
    )
    await conn.commit()

    source = DatabaseOverrideSource(WatchConfig, "watch")
    assert "not_a_field" not in source()
