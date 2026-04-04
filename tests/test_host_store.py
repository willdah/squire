"""Tests for HostStore — enrollment, removal, verification, and loading."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from squire.hosts.store import EnrollmentResult, HostStore
from squire.system.registry import BackendRegistry


@pytest_asyncio.fixture
async def store(tmp_path):
    """Create a HostStore with real DB and registry, mocked key dir."""
    from squire.database.service import DatabaseService

    db = DatabaseService(tmp_path / "test.db")
    registry = BackendRegistry()
    keys_dir = tmp_path / "keys"
    with patch("squire.hosts.store.keys._keys_dir", return_value=keys_dir):
        s = HostStore(db, registry)
        yield s
    await db.close()


@pytest_asyncio.fixture
async def store_parts(tmp_path):
    """Expose db, registry, and store for fine-grained assertions."""
    from squire.database.service import DatabaseService

    db = DatabaseService(tmp_path / "test.db")
    registry = BackendRegistry()
    keys_dir = tmp_path / "keys"
    with patch("squire.hosts.store.keys._keys_dir", return_value=keys_dir):
        s = HostStore(db, registry)
        yield s, db, registry, keys_dir
    await db.close()


class TestEnroll:
    @pytest.mark.asyncio
    async def test_manual_fallback_when_ssh_fails(self, store_parts):
        store, db, registry, keys_dir = store_parts
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            result = await store.enroll(name="srv", address="10.0.0.1", user="will")

        assert isinstance(result, EnrollmentResult)
        assert result.status == "pending_key"
        assert result.public_key.startswith("ssh-ed25519 ")
        assert "squire-managed:srv" in result.public_key
        host = await db.get_managed_host("srv")
        assert host is not None
        assert host["status"] == "pending_key"
        assert "srv" in registry.host_names

    @pytest.mark.asyncio
    async def test_auto_deploy_when_ssh_succeeds(self, store_parts):
        store, db, registry, keys_dir = store_parts

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        mock_conn.get_extra_info = MagicMock(return_value=None)
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()

        with patch("squire.hosts.store.asyncssh.connect", new=AsyncMock(return_value=mock_conn)):
            result = await store.enroll(name="srv", address="10.0.0.1", user="will")

        assert result.status == "active"
        host = await db.get_managed_host("srv")
        assert host["status"] == "active"
        assert "srv" in registry.host_names

    @pytest.mark.asyncio
    async def test_rejects_local_name(self, store):
        with pytest.raises(ValueError, match="local"):
            await store.enroll(name="local", address="10.0.0.1")

    @pytest.mark.asyncio
    async def test_rejects_duplicate_name(self, store):
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            await store.enroll(name="srv", address="10.0.0.1")
        with pytest.raises(ValueError, match="already exists"):
            await store.enroll(name="srv", address="10.0.0.2")


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_deletes_everything(self, store_parts):
        store, db, registry, keys_dir = store_parts
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            await store.enroll(name="srv", address="10.0.0.1")
        await store.remove("srv")
        assert await db.get_managed_host("srv") is None
        assert "srv" not in registry.host_names
        assert not (keys_dir / "srv").exists()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_raises(self, store):
        with pytest.raises(ValueError, match="not found"):
            await store.remove("ghost")


class TestVerify:
    @pytest.mark.asyncio
    async def test_verify_success_updates_status(self, store_parts):
        store, db, registry, keys_dir = store_parts
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            await store.enroll(name="srv", address="10.0.0.1")

        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()
        with patch("squire.hosts.store.asyncssh.connect", new=AsyncMock(return_value=mock_conn)):
            result = await store.verify("srv")

        assert result is True
        host = await db.get_managed_host("srv")
        assert host["status"] == "active"

    @pytest.mark.asyncio
    async def test_verify_failure_returns_false(self, store_parts):
        store, db, registry, keys_dir = store_parts
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            await store.enroll(name="srv", address="10.0.0.1")
            result = await store.verify("srv")
        assert result is False


class TestLoad:
    @pytest.mark.asyncio
    async def test_load_registers_active_hosts(self, store_parts):
        store, db, registry, keys_dir = store_parts
        await db.save_managed_host(
            name="loaded-host",
            address="10.0.0.50",
            user="admin",
            key_file=str(keys_dir / "loaded-host"),
            status="active",
        )
        await store.load()
        assert "loaded-host" in registry.host_names

    @pytest.mark.asyncio
    async def test_load_registers_pending_hosts(self, store_parts):
        store, db, registry, keys_dir = store_parts
        await db.save_managed_host(
            name="pending-host",
            address="10.0.0.51",
            key_file=str(keys_dir / "pending-host"),
            status="pending_key",
        )
        await store.load()
        assert "pending-host" in registry.host_names


class TestListAndGet:
    @pytest.mark.asyncio
    async def test_list_hosts(self, store):
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            await store.enroll(name="a", address="10.0.0.1")
            await store.enroll(name="b", address="10.0.0.2")
        hosts = await store.list_hosts()
        assert len(hosts) == 2

    @pytest.mark.asyncio
    async def test_get_host(self, store):
        with patch("squire.hosts.store.asyncssh.connect", side_effect=OSError("refused")):
            await store.enroll(name="srv", address="10.0.0.1")
        host = await store.get_host("srv")
        assert host is not None
        assert host.name == "srv"

    @pytest.mark.asyncio
    async def test_get_host_missing(self, store):
        assert await store.get_host("ghost") is None
