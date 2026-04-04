"""Tests for watch loop helpers: command polling and interruptible sleep."""

import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_poll_commands_stop(db):
    """A 'stop' command should set the shutdown event."""
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    await db.insert_watch_command("stop")

    await _poll_commands(db, shutdown, watch_config=None)
    assert shutdown.is_set()

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_poll_commands_update_config(db):
    """An 'update_config' command should apply overrides."""
    from squire.config import WatchConfig
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    config = WatchConfig()

    await db.insert_watch_command("update_config", payload=json.dumps({"interval_minutes": 1}))
    await _poll_commands(db, shutdown, watch_config=config)

    assert config.interval_minutes == 1
    assert not shutdown.is_set()

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_poll_commands_unknown_fails(db):
    """Unknown commands should be marked as failed."""
    from squire.watch import _poll_commands

    shutdown = asyncio.Event()
    await db.insert_watch_command("unknown_cmd")

    await _poll_commands(db, shutdown, watch_config=None)

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_interruptible_sleep_responds_to_commands(db):
    """Sleep should break out when a stop command is inserted."""
    from squire.watch import _interruptible_sleep

    shutdown = asyncio.Event()

    async def insert_stop():
        await asyncio.sleep(0.2)
        await db.insert_watch_command("stop")

    asyncio.create_task(insert_stop())
    await _interruptible_sleep(db, shutdown, interval_seconds=60, poll_seconds=0.1, watch_config=None)
    assert shutdown.is_set()
