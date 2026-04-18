"""Tests for DatabaseService config_overrides accessors."""

import pytest


@pytest.mark.asyncio
async def test_set_and_get_single_override(db):
    await db.set_config_override("watch", "interval_minutes", 7)
    stored = await db.get_config_overrides("watch")
    assert stored == {"interval_minutes": 7}


@pytest.mark.asyncio
async def test_set_section_overrides_upserts(db):
    await db.set_config_section_overrides("watch", {"interval_minutes": 3, "notify_on_action": False})
    await db.set_config_section_overrides("watch", {"interval_minutes": 12})  # upsert
    stored = await db.get_config_overrides("watch")
    assert stored == {"interval_minutes": 12, "notify_on_action": False}


@pytest.mark.asyncio
async def test_delete_single_field(db):
    await db.set_config_section_overrides("watch", {"interval_minutes": 2, "notify_on_action": True})
    removed = await db.delete_config_override("watch", "interval_minutes")
    assert removed is True
    stored = await db.get_config_overrides("watch")
    assert stored == {"notify_on_action": True}


@pytest.mark.asyncio
async def test_delete_missing_field_returns_false(db):
    result = await db.delete_config_override("watch", "nothing")
    assert result is False


@pytest.mark.asyncio
async def test_clear_section(db):
    await db.set_config_section_overrides("watch", {"interval_minutes": 5, "notify_on_action": False})
    await db.set_config_section_overrides("llm", {"temperature": 0.3})

    count = await db.clear_config_section("watch")
    assert count == 2
    assert await db.get_config_overrides("watch") == {}
    # Other section untouched.
    assert await db.get_config_overrides("llm") == {"temperature": 0.3}


@pytest.mark.asyncio
async def test_get_all_returns_grouped(db):
    await db.set_config_section_overrides("watch", {"interval_minutes": 9})
    await db.set_config_section_overrides("llm", {"temperature": 0.9})
    grouped = await db.get_all_config_overrides()
    assert grouped == {"watch": {"interval_minutes": 9}, "llm": {"temperature": 0.9}}


@pytest.mark.asyncio
async def test_complex_values_roundtrip(db):
    payload = {
        "webhooks": [{"name": "discord", "url": "https://example.invalid", "events": ["*"]}],
        "enabled": True,
    }
    await db.set_config_section_overrides("notifications", payload)
    stored = await db.get_config_overrides("notifications")
    assert stored == payload
