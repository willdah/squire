"""Tests for managed_hosts database methods."""

import json

import pytest


class TestManagedHostsCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get(self, db):
        await db.save_managed_host(
            name="test-host",
            address="10.0.0.5",
            user="will",
            port=22,
            key_file="/path/to/key",
            tags=["web", "docker"],
            services=["nginx"],
            service_root="/opt",
            status="active",
        )
        host = await db.get_managed_host("test-host")
        assert host is not None
        assert host["name"] == "test-host"
        assert host["address"] == "10.0.0.5"
        assert host["user"] == "will"
        assert host["port"] == 22
        assert host["key_file"] == "/path/to/key"
        assert json.loads(host["tags"]) == ["web", "docker"]
        assert json.loads(host["services"]) == ["nginx"]
        assert host["service_root"] == "/opt"
        assert host["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        assert await db.get_managed_host("missing") is None

    @pytest.mark.asyncio
    async def test_list_managed_hosts(self, db):
        await db.save_managed_host(
            name="host-a",
            address="10.0.0.1",
            key_file="/k/a",
            status="active",
        )
        await db.save_managed_host(
            name="host-b",
            address="10.0.0.2",
            key_file="/k/b",
            status="pending_key",
        )
        hosts = await db.list_managed_hosts()
        assert len(hosts) == 2
        names = {h["name"] for h in hosts}
        assert names == {"host-a", "host-b"}

    @pytest.mark.asyncio
    async def test_delete_managed_host(self, db):
        await db.save_managed_host(
            name="host-a",
            address="10.0.0.1",
            key_file="/k/a",
            status="active",
        )
        assert await db.delete_managed_host("host-a") is True
        assert await db.get_managed_host("host-a") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        assert await db.delete_managed_host("missing") is False

    @pytest.mark.asyncio
    async def test_update_status(self, db):
        await db.save_managed_host(
            name="host-a",
            address="10.0.0.1",
            key_file="/k/a",
            status="pending_key",
        )
        assert await db.update_managed_host_status("host-a", "active") is True
        host = await db.get_managed_host("host-a")
        assert host["status"] == "active"

    @pytest.mark.asyncio
    async def test_update_status_nonexistent(self, db):
        assert await db.update_managed_host_status("missing", "active") is False

    @pytest.mark.asyncio
    async def test_save_upserts(self, db):
        await db.save_managed_host(
            name="host-a",
            address="10.0.0.1",
            key_file="/k/a",
            status="pending_key",
        )
        await db.save_managed_host(
            name="host-a",
            address="10.0.0.2",
            key_file="/k/a",
            status="active",
        )
        host = await db.get_managed_host("host-a")
        assert host["address"] == "10.0.0.2"
        assert host["status"] == "active"
