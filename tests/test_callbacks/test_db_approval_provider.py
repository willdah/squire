"""Tests for DatabaseApprovalProvider."""

import asyncio

import pytest

from squire.approval import AsyncApprovalProvider
from squire.callbacks.db_approval_provider import DatabaseApprovalProvider
from squire.watch_emitter import WatchEventEmitter


@pytest.mark.asyncio
async def test_satisfies_async_protocol(db):
    emitter = WatchEventEmitter(db)
    provider = DatabaseApprovalProvider(db=db, emitter=emitter, cycle=1)
    assert isinstance(provider, AsyncApprovalProvider)


@pytest.mark.asyncio
async def test_approval_approved(db):
    emitter = WatchEventEmitter(db)
    provider = DatabaseApprovalProvider(db=db, emitter=emitter, cycle=1, timeout=5.0)

    async def approve_first_pending():
        await asyncio.sleep(0.3)
        for _ in range(10):
            conn = await db._get_conn()
            cursor = await conn.execute("SELECT request_id FROM watch_approvals WHERE status = 'pending' LIMIT 1")
            row = await cursor.fetchone()
            if row:
                await db.update_watch_approval(row[0], "approved")
                return
            await asyncio.sleep(0.1)

    task = asyncio.create_task(approve_first_pending())
    result = await provider.request_approval_async("restart_container", {"container": "nginx"}, 4)
    await task
    assert result is True


@pytest.mark.asyncio
async def test_approval_denied(db):
    emitter = WatchEventEmitter(db)
    provider = DatabaseApprovalProvider(db=db, emitter=emitter, cycle=1, timeout=5.0)

    async def deny_first_pending():
        await asyncio.sleep(0.3)
        for _ in range(10):
            conn = await db._get_conn()
            cursor = await conn.execute("SELECT request_id FROM watch_approvals WHERE status = 'pending' LIMIT 1")
            row = await cursor.fetchone()
            if row:
                await db.update_watch_approval(row[0], "denied")
                return
            await asyncio.sleep(0.1)

    task = asyncio.create_task(deny_first_pending())
    result = await provider.request_approval_async("restart_container", {"container": "nginx"}, 4)
    await task
    assert result is False


@pytest.mark.asyncio
async def test_approval_timeout(db):
    emitter = WatchEventEmitter(db)
    provider = DatabaseApprovalProvider(db=db, emitter=emitter, cycle=1, timeout=0.5, poll_interval=0.1)

    result = await provider.request_approval_async("restart_container", {}, 4)
    assert result is False

    conn = await db._get_conn()
    cursor = await conn.execute("SELECT status FROM watch_approvals WHERE status = 'expired' LIMIT 1")
    row = await cursor.fetchone()
    assert row is not None
