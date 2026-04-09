# Host Enrollment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TOML-based host configuration with managed SSH enrollment — Squire generates per-host keys, auto-deploys via existing SSH access, and provides CLI + web CRUD with no restart required.

**Architecture:** New `HostStore` service coordinates key management (`system/keys.py`), database persistence (`managed_hosts` table), and runtime registry updates. CLI and API both delegate to `HostStore`. TOML `[[hosts]]` loading is removed entirely (clean break).

**Tech Stack:** Python 3.12+, asyncssh (key generation + SSH), aiosqlite (persistence), Typer (CLI), FastAPI (API), Next.js + shadcn/ui (web)

**Spec:** `docs/superpowers/specs/2026-04-04-host-enrollment-design.md`

---

### Task 1: SSH Key Management Module

**Files:**
- Create: `src/squire/system/keys.py`
- Create: `tests/test_keys.py`

- [ ] **Step 1: Write failing tests for key management**

Create `tests/test_keys.py`:

```python
"""Tests for SSH key management."""

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from squire.system.keys import delete_key, generate_key, get_key_path, get_public_key


@pytest.fixture
def keys_dir(tmp_path):
    """Redirect key storage to a temp directory."""
    d = tmp_path / "keys"
    with patch("squire.system.keys._keys_dir", return_value=d):
        yield d


class TestGenerateKey:
    def test_creates_key_pair(self, keys_dir):
        private_path, public_text = generate_key("test-host")
        assert private_path.exists()
        assert private_path.name == "test-host"
        pub_path = keys_dir / "test-host.pub"
        assert pub_path.exists()
        assert public_text.startswith("ssh-ed25519 ")
        assert "squire-managed:test-host" in public_text

    def test_private_key_permissions(self, keys_dir):
        private_path, _ = generate_key("test-host")
        mode = private_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600

    def test_keys_dir_created_with_correct_permissions(self, keys_dir):
        generate_key("test-host")
        mode = keys_dir.stat().st_mode
        assert stat.S_IMODE(mode) == 0o700

    def test_raises_on_duplicate(self, keys_dir):
        generate_key("test-host")
        with pytest.raises(FileExistsError):
            generate_key("test-host")


class TestGetKeyPath:
    def test_returns_path_when_exists(self, keys_dir):
        generate_key("test-host")
        assert get_key_path("test-host") == keys_dir / "test-host"

    def test_returns_none_when_missing(self, keys_dir):
        assert get_key_path("nonexistent") is None


class TestGetPublicKey:
    def test_returns_public_key_text(self, keys_dir):
        _, expected_text = generate_key("test-host")
        assert get_public_key("test-host") == expected_text

    def test_returns_none_when_missing(self, keys_dir):
        assert get_public_key("nonexistent") is None


class TestDeleteKey:
    def test_deletes_existing_key(self, keys_dir):
        generate_key("test-host")
        assert delete_key("test-host") is True
        assert not (keys_dir / "test-host").exists()
        assert not (keys_dir / "test-host.pub").exists()

    def test_returns_false_for_missing(self, keys_dir):
        assert delete_key("nonexistent") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_keys.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squire.system.keys'`

- [ ] **Step 3: Implement key management module**

Create `src/squire/system/keys.py`:

```python
"""SSH key management — generate, retrieve, and delete ed25519 key pairs.

Keys are stored in ~/.config/squire/keys/ with one file per host:
  {name}       — private key (mode 0600)
  {name}.pub   — public key (mode 0644)
"""

from __future__ import annotations

import os
from pathlib import Path

import asyncssh


def _keys_dir() -> Path:
    """Return the keys storage directory."""
    return Path.home() / ".config" / "squire" / "keys"


def generate_key(name: str) -> tuple[Path, str]:
    """Generate an ed25519 key pair for a host.

    Returns:
        Tuple of (private_key_path, public_key_text).

    Raises:
        FileExistsError: If a key already exists for this host name.
    """
    keys = _keys_dir()
    keys.mkdir(parents=True, exist_ok=True)
    os.chmod(keys, 0o700)

    private_path = keys / name
    pub_path = keys / f"{name}.pub"

    if private_path.exists():
        raise FileExistsError(f"Key already exists for host '{name}': {private_path}")

    key = asyncssh.generate_private_key("ssh-ed25519")
    comment = f"squire-managed:{name}"

    private_path.write_bytes(key.export_private_key())
    os.chmod(private_path, 0o600)

    public_text = key.export_public_key("openssh").decode().strip() + f" {comment}"
    pub_path.write_text(public_text + "\n")
    os.chmod(pub_path, 0o644)

    return private_path, public_text


def get_key_path(name: str) -> Path | None:
    """Return the private key path if it exists, else None."""
    path = _keys_dir() / name
    return path if path.exists() else None


def get_public_key(name: str) -> str | None:
    """Return the public key text if it exists, else None."""
    path = _keys_dir() / f"{name}.pub"
    if not path.exists():
        return None
    return path.read_text().strip()


def delete_key(name: str) -> bool:
    """Delete the key pair for a host. Returns True if files existed."""
    keys = _keys_dir()
    private_path = keys / name
    pub_path = keys / f"{name}.pub"
    existed = private_path.exists() or pub_path.exists()
    private_path.unlink(missing_ok=True)
    pub_path.unlink(missing_ok=True)
    return existed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_keys.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/system/keys.py tests/test_keys.py
git commit -m "feat(hosts): add SSH key management module"
```

---

### Task 2: Database Schema and CRUD for Managed Hosts

**Files:**
- Modify: `src/squire/database/service.py`
- Create: `tests/test_managed_hosts_db.py`

- [ ] **Step 1: Write failing tests for managed hosts DB methods**

Create `tests/test_managed_hosts_db.py`:

```python
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
            name="host-a", address="10.0.0.1", key_file="/k/a", status="active",
        )
        await db.save_managed_host(
            name="host-b", address="10.0.0.2", key_file="/k/b", status="pending_key",
        )
        hosts = await db.list_managed_hosts()
        assert len(hosts) == 2
        names = {h["name"] for h in hosts}
        assert names == {"host-a", "host-b"}

    @pytest.mark.asyncio
    async def test_delete_managed_host(self, db):
        await db.save_managed_host(
            name="host-a", address="10.0.0.1", key_file="/k/a", status="active",
        )
        assert await db.delete_managed_host("host-a") is True
        assert await db.get_managed_host("host-a") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        assert await db.delete_managed_host("missing") is False

    @pytest.mark.asyncio
    async def test_update_status(self, db):
        await db.save_managed_host(
            name="host-a", address="10.0.0.1", key_file="/k/a", status="pending_key",
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
            name="host-a", address="10.0.0.1", key_file="/k/a", status="pending_key",
        )
        await db.save_managed_host(
            name="host-a", address="10.0.0.2", key_file="/k/a", status="active",
        )
        host = await db.get_managed_host("host-a")
        assert host["address"] == "10.0.0.2"
        assert host["status"] == "active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_managed_hosts_db.py -v`
Expected: FAIL — `AttributeError: 'DatabaseService' object has no attribute 'save_managed_host'`

- [ ] **Step 3: Add managed_hosts table and CRUD methods to DatabaseService**

In `src/squire/database/service.py`, add the table DDL after the existing `_CREATE_WATCH_APPROVALS` constant (around line 138):

```python
_CREATE_MANAGED_HOSTS = """
CREATE TABLE IF NOT EXISTS managed_hosts (
    name         TEXT PRIMARY KEY,
    address      TEXT NOT NULL,
    user         TEXT NOT NULL DEFAULT 'root',
    port         INTEGER NOT NULL DEFAULT 22,
    key_file     TEXT NOT NULL,
    tags         TEXT NOT NULL DEFAULT '[]',
    services     TEXT NOT NULL DEFAULT '[]',
    service_root TEXT NOT NULL DEFAULT '/opt',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""
```

Add `_CREATE_MANAGED_HOSTS` to the schema list in `_ensure_schema()` (after `_CREATE_WATCH_APPROVALS` in the tuple around line 183).

Then add these methods to the `DatabaseService` class at the end (before the `close` method):

```python
    # --- Managed Hosts ---

    async def save_managed_host(
        self,
        *,
        name: str,
        address: str,
        key_file: str,
        status: str = "active",
        user: str = "root",
        port: int = 22,
        tags: list[str] | None = None,
        services: list[str] | None = None,
        service_root: str = "/opt",
    ) -> None:
        """Insert or replace a managed host."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT OR REPLACE INTO managed_hosts
                (name, address, user, port, key_file, tags, services, service_root, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                address,
                user,
                port,
                key_file,
                json.dumps(tags or []),
                json.dumps(services or []),
                service_root,
                status,
                now,
                now,
            ),
        )
        await conn.commit()

    async def list_managed_hosts(self) -> list[dict]:
        """List all managed hosts."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM managed_hosts ORDER BY name")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_managed_host(self, name: str) -> dict | None:
        """Get a managed host by name."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM managed_hosts WHERE name = ?", (name,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_managed_host(self, name: str) -> bool:
        """Delete a managed host by name. Returns True if deleted."""
        conn = await self._get_conn()
        cursor = await conn.execute("DELETE FROM managed_hosts WHERE name = ?", (name,))
        await conn.commit()
        return cursor.rowcount > 0

    async def update_managed_host_status(self, name: str, status: str) -> bool:
        """Update a managed host's status. Returns True if updated."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "UPDATE managed_hosts SET status = ?, updated_at = ? WHERE name = ?",
            (status, now, name),
        )
        await conn.commit()
        return cursor.rowcount > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_managed_hosts_db.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest -v`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/squire/database/service.py tests/test_managed_hosts_db.py
git commit -m "feat(hosts): add managed_hosts database table and CRUD"
```

---

### Task 3: Registry Runtime Mutations

**Files:**
- Modify: `src/squire/system/registry.py`
- Modify: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests for add_host and remove_host**

Append to `tests/test_registry.py`:

```python
    def test_add_host(self):
        registry = BackendRegistry()
        config = HostConfig(name="new-host", address="10.0.0.99")
        registry.add_host(config)
        assert "new-host" in registry.host_names
        backend = registry.get("new-host")
        assert backend is not None

    def test_add_host_evicts_stale_backend(self):
        hosts = [HostConfig(name="srv", address="10.0.0.1")]
        registry = BackendRegistry(hosts)
        b1 = registry.get("srv")
        # Re-add with different address
        registry.add_host(HostConfig(name="srv", address="10.0.0.2"))
        b2 = registry.get("srv")
        assert b1 is not b2

    @pytest.mark.asyncio
    async def test_remove_host(self):
        hosts = [HostConfig(name="srv", address="10.0.0.1")]
        registry = BackendRegistry(hosts)
        await registry.remove_host("srv")
        assert "srv" not in registry.host_names
        with pytest.raises(ValueError, match="Unknown host"):
            registry.get("srv")

    @pytest.mark.asyncio
    async def test_remove_host_nonexistent_is_noop(self):
        registry = BackendRegistry()
        await registry.remove_host("ghost")  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry.py -v -k "add_host or remove_host"`
Expected: FAIL — `AttributeError: 'BackendRegistry' object has no attribute 'add_host'`

- [ ] **Step 3: Add add_host and remove_host to BackendRegistry**

In `src/squire/system/registry.py`, add these two methods after the `get` method (after line 42):

```python
    def add_host(self, config: HostConfig) -> None:
        """Register a new host at runtime. Evicts any stale cached backend."""
        self._hosts[config.name] = config
        self._backends.pop(config.name, None)

    async def remove_host(self, name: str) -> None:
        """Remove a host at runtime. Closes the backend if active."""
        self._hosts.pop(name, None)
        backend = self._backends.pop(name, None)
        if backend is not None:
            await backend.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry.py -v`
Expected: All tests PASS (existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/squire/system/registry.py tests/test_registry.py
git commit -m "feat(hosts): add runtime add_host/remove_host to BackendRegistry"
```

---

### Task 4: HostStore Service

**Files:**
- Create: `src/squire/hosts/__init__.py`
- Create: `src/squire/hosts/store.py`
- Create: `tests/test_host_store.py`

- [ ] **Step 1: Create the hosts package**

Create `src/squire/hosts/__init__.py`:

```python
"""Host enrollment and management."""
```

- [ ] **Step 2: Write failing tests for HostStore**

Create `tests/test_host_store.py`:

```python
"""Tests for HostStore — enrollment, removal, verification, and loading."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from squire.database.service import DatabaseService
from squire.hosts.store import EnrollmentResult, HostStore
from squire.system.registry import BackendRegistry


@pytest_asyncio.fixture
async def store(tmp_path):
    """Create a HostStore with real DB and registry, mocked key dir."""
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
        # Saved in DB
        host = await db.get_managed_host("srv")
        assert host is not None
        assert host["status"] == "pending_key"
        # Registered in registry
        assert "srv" in registry.host_names

    @pytest.mark.asyncio
    async def test_auto_deploy_when_ssh_succeeds(self, store_parts):
        store, db, registry, keys_dir = store_parts

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        mock_conn.get_extra_info = MagicMock(return_value=None)
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()

        with (
            patch("squire.hosts.store.asyncssh.connect", return_value=mock_conn),
            patch("squire.hosts.store.asyncssh.import_known_hosts"),
            patch("squire.hosts.store.asyncssh.read_known_hosts", return_value=()),
        ):
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
        with patch("squire.hosts.store.asyncssh.connect", return_value=mock_conn):
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
        # Manually insert a host in the DB
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_host_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squire.hosts.store'`

- [ ] **Step 4: Implement HostStore**

Create `src/squire/hosts/store.py`:

```python
"""HostStore — centralized host enrollment, removal, and verification.

Single entry point for all host mutations. Coordinates key management,
database persistence, and runtime registry updates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import asyncssh
from pydantic import BaseModel

from ..config.hosts import HostConfig
from ..database.service import DatabaseService
from ..system import keys
from ..system.registry import BackendRegistry

logger = logging.getLogger(__name__)


class EnrollmentResult(BaseModel):
    """Result of a host enrollment attempt."""

    name: str
    status: str  # "active" or "pending_key"
    public_key: str
    message: str


class HostStore:
    """Centralized host management — enrollment, removal, verification."""

    def __init__(self, db: DatabaseService, registry: BackendRegistry) -> None:
        self._db = db
        self._registry = registry

    async def load(self) -> None:
        """Load all managed hosts from DB into the registry. Called at startup."""
        hosts = await self._db.list_managed_hosts()
        for row in hosts:
            config = self._row_to_config(row)
            self._registry.add_host(config)
            logger.info("Loaded managed host '%s' (%s)", config.name, row["status"])

    async def enroll(
        self,
        name: str,
        address: str,
        user: str = "root",
        port: int = 22,
        tags: list[str] | None = None,
        services: list[str] | None = None,
        service_root: str = "/opt",
    ) -> EnrollmentResult:
        """Enroll a new host: generate key, attempt deploy, persist, register."""
        if name == "local":
            raise ValueError("Cannot enroll a host named 'local' — reserved for the local machine")

        existing = await self._db.get_managed_host(name)
        if existing is not None:
            raise ValueError(f"Host '{name}' already exists")

        # Generate SSH key pair
        key_path, public_key = keys.generate_key(name)

        # Attempt auto-deploy via existing SSH credentials
        status = "pending_key"
        message = ""
        try:
            status, message = await self._auto_deploy(
                name=name,
                address=address,
                user=user,
                port=port,
                key_path=key_path,
                public_key=public_key,
            )
        except Exception as exc:
            logger.debug("Auto-deploy failed for '%s': %s", name, exc)
            message = f"Could not connect to {address} with existing SSH credentials."

        # Persist to database
        await self._db.save_managed_host(
            name=name,
            address=address,
            user=user,
            port=port,
            key_file=str(key_path),
            tags=tags,
            services=services,
            service_root=service_root,
            status=status,
        )

        # Register in the runtime registry
        config = HostConfig(
            name=name,
            address=address,
            user=user,
            port=port,
            key_file=str(key_path),
            tags=tags or [],
            services=services or [],
            service_root=service_root,
        )
        self._registry.add_host(config)

        return EnrollmentResult(
            name=name,
            status=status,
            public_key=public_key,
            message=message,
        )

    async def _auto_deploy(
        self,
        *,
        name: str,
        address: str,
        user: str,
        port: int,
        key_path: Path,
        public_key: str,
    ) -> tuple[str, str]:
        """Try to deploy the public key via existing SSH access.

        Returns (status, message) tuple.
        """
        # Connect using existing credentials (agent / default keys)
        conn = await asyncssh.connect(
            address,
            port=port,
            username=user,
            known_hosts=None,  # user is explicitly trusting this host
        )
        try:
            # Add host key to known_hosts for future strict connections
            await self._save_host_key(conn, address, port)

            # Deploy public key to authorized_keys
            await conn.run("mkdir -p ~/.ssh && chmod 700 ~/.ssh", check=True)
            append_cmd = f'echo "{public_key}" >> ~/.ssh/authorized_keys'
            await conn.run(append_cmd, check=True)
            await conn.run("chmod 600 ~/.ssh/authorized_keys", check=True)
        finally:
            conn.close()
            await conn.wait_closed()

        # Verify the managed key works
        try:
            test_conn = await asyncssh.connect(
                address,
                port=port,
                username=user,
                client_keys=[str(key_path)],
                known_hosts=None,
            )
            test_conn.close()
            await test_conn.wait_closed()
        except Exception as exc:
            logger.warning("Managed key verification failed for '%s': %s", name, exc)
            return "pending_key", f"Key deployed but verification failed: {exc}"

        return "active", f"Deployed key to {user}@{address} via existing SSH access."

    async def _save_host_key(
        self,
        conn: asyncssh.SSHClientConnection,
        address: str,
        port: int,
    ) -> None:
        """Save the remote host key to ~/.ssh/known_hosts."""
        peer_host_key = conn.get_extra_info("peer_host_key")
        if peer_host_key is None:
            return

        known_hosts_path = Path.home() / ".ssh" / "known_hosts"
        known_hosts_path.parent.mkdir(parents=True, exist_ok=True)

        # Build the host entry
        if port == 22:
            host_entry = address
        else:
            host_entry = f"[{address}]:{port}"

        key_type = peer_host_key.get_algorithm()
        key_data = peer_host_key.export_public_key("openssh").decode().strip()
        line = f"{host_entry} {key_data}\n"

        # Append if not already present
        existing = known_hosts_path.read_text() if known_hosts_path.exists() else ""
        if host_entry not in existing:
            with open(known_hosts_path, "a") as f:
                f.write(line)

    async def remove(self, name: str) -> None:
        """Remove a managed host: delete key, DB row, and registry entry."""
        existing = await self._db.get_managed_host(name)
        if existing is None:
            raise ValueError(f"Host '{name}' not found")

        keys.delete_key(name)
        await self._db.delete_managed_host(name)
        await self._registry.remove_host(name)

    async def verify(self, name: str) -> bool:
        """Test connectivity using the managed key. Updates status on success."""
        host = await self._db.get_managed_host(name)
        if host is None:
            raise ValueError(f"Host '{name}' not found")

        key_path = keys.get_key_path(name)
        if key_path is None:
            return False

        try:
            conn = await asyncssh.connect(
                host["address"],
                port=host["port"],
                username=host["user"],
                client_keys=[str(key_path)],
                known_hosts=None,
            )
            conn.close()
            await conn.wait_closed()
        except Exception:
            return False

        if host["status"] != "active":
            await self._db.update_managed_host_status(name, "active")
        return True

    async def list_hosts(self) -> list[HostConfig]:
        """Return all managed hosts as HostConfig objects."""
        rows = await self._db.list_managed_hosts()
        return [self._row_to_config(row) for row in rows]

    async def get_host(self, name: str) -> HostConfig | None:
        """Return a single managed host as HostConfig, or None."""
        row = await self._db.get_managed_host(name)
        if row is None:
            return None
        return self._row_to_config(row)

    @staticmethod
    def _row_to_config(row: dict) -> HostConfig:
        """Convert a DB row dict to a HostConfig."""
        return HostConfig(
            name=row["name"],
            address=row["address"],
            user=row["user"],
            port=row["port"],
            key_file=row["key_file"],
            tags=json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"],
            services=json.loads(row["services"]) if isinstance(row["services"], str) else row["services"],
            service_root=row["service_root"],
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_host_store.py -v`
Expected: All 13 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/squire/hosts/__init__.py src/squire/hosts/store.py tests/test_host_store.py
git commit -m "feat(hosts): add HostStore service for enrollment and management"
```

---

### Task 5: Remove TOML Host Loading and Wire HostStore at Startup

**Files:**
- Modify: `src/squire/api/app.py`
- Modify: `src/squire/api/dependencies.py`
- Modify: `src/squire/main.py`
- Modify: `src/squire/watch.py`
- Modify: `src/squire/agent.py`
- Modify: `src/squire/api/routers/config.py`

- [ ] **Step 1: Update `api/dependencies.py` — add host_store, remove host_configs**

In `src/squire/api/dependencies.py`:

Replace the `host_configs` line and `HostConfig` import. Add `HostStore` import and singleton:

```python
# Add import at top:
from squire.hosts.store import HostStore

# Replace line 27 (host_configs: list[HostConfig] = []) with:
host_store: HostStore | None = None

# Add getter function after get_skills_service():
def get_host_store() -> HostStore:
    if host_store is None:
        raise RuntimeError("HostStore not initialized")
    return host_store
```

Remove the `HostConfig` import from line 8 since it's no longer used here.

- [ ] **Step 2: Update `api/app.py` — replace TOML loading with HostStore**

In `src/squire/api/app.py`:

Remove these imports (lines 24-25):
```python
from ..config.hosts import HostConfig
from ..config.loader import get_list_section
```

Add this import:
```python
from ..hosts.store import HostStore
```

In the `lifespan` function, replace lines 82-86 (TOML host loading and registry creation):
```python
    # Load host configs
    host_dicts = get_list_section("hosts")
    deps.host_configs = [HostConfig(**h) for h in host_dicts]

    # Create service singletons
    deps.registry = BackendRegistry(deps.host_configs)
```

With:
```python
    # Create service singletons
    deps.registry = BackendRegistry()
```

After `deps.db = DatabaseService(deps.db_config.path)` (line 87), add:
```python
    # Initialize host store and load managed hosts
    deps.host_store = HostStore(deps.db, deps.registry)
    await deps.host_store.load()
```

- [ ] **Step 3: Update `main.py` — replace TOML loading with HostStore**

In `src/squire/main.py`:

Remove these imports (lines 18-19):
```python
from .config.hosts import HostConfig
from .config.loader import get_list_section
```

Add this import:
```python
from .hosts.store import HostStore
```

In the former `start_chat()` path (removed with the TUI; same pattern applies to web chat and watch startup), replace lines 142-144:
```python
    host_dicts = get_list_section("hosts")
    hosts = [HostConfig(**h) for h in host_dicts]
    registry = BackendRegistry(hosts)
```

With:
```python
    registry = BackendRegistry()
```

After `set_db(db)` (line ~148 after adjustment), add:
```python
    # Load managed hosts into registry
    host_store = HostStore(db, registry)
    await host_store.load()
```

- [ ] **Step 4: Update `watch.py` — replace TOML loading with HostStore**

In `src/squire/watch.py`:

Remove these imports (lines 34-35):
```python
from .config.hosts import HostConfig
from .config.loader import get_list_section
```

Add this import:
```python
from .hosts.store import HostStore
```

In `start_watch()`, replace lines 128-130:
```python
    host_dicts = get_list_section("hosts")
    hosts = [HostConfig(**h) for h in host_dicts]
    registry = BackendRegistry(hosts)
```

With:
```python
    registry = BackendRegistry()
```

After `set_db(db)` (~line 135 after adjustment), add:
```python
    # Load managed hosts into registry
    host_store = HostStore(db, registry)
    await host_store.load()
```

- [ ] **Step 5: Update `agent.py` — replace TOML loading with HostStore**

In `src/squire/agent.py`:

Remove these imports (lines 17-18):
```python
from .config.hosts import HostConfig
from .config.loader import get_list_section
```

Add this import:
```python
import asyncio
from .hosts.store import HostStore
```

Replace lines 27-29:
```python
_host_dicts = get_list_section("hosts")
_hosts = [HostConfig(**h) for h in _host_dicts]
_registry = BackendRegistry(_hosts)
```

With:
```python
_registry = BackendRegistry()
```

After `set_notifier(_notifier)` (line ~38), add:
```python
_host_store = HostStore(_db, _registry)
asyncio.get_event_loop().run_until_complete(_host_store.load())
```

Note: `agent.py` runs at module import time for ADK CLI. The `asyncio.get_event_loop().run_until_complete()` pattern is needed since there's no running async context at module level. If this module is not being used in production, this can be simplified later.

- [ ] **Step 6: Update `api/routers/config.py` — use host_store instead of host_configs**

In `src/squire/api/routers/config.py`:

Replace line 45:
```python
        hosts=[h.model_dump(mode="json") for h in deps.host_configs],
```

With:
```python
        hosts=[h.model_dump(mode="json") for h in (await deps.get_host_store().list_hosts())] if deps.host_store else [],
```

Wait — that's awkward in a sync context. Since `list_hosts` is async, and the config endpoint is already async, adjust:

Replace the entire `get_config` function body:
```python
@router.get("", response_model=ConfigResponse)
async def get_config(
    app_config=Depends(get_app_config),
    llm_config=Depends(get_llm_config),
):
    """Current effective configuration (all sections), with sensitive values redacted."""
    host_configs = []
    if deps.host_store is not None:
        hosts = await deps.host_store.list_hosts()
        host_configs = [h.model_dump(mode="json") for h in hosts]
    return ConfigResponse(
        app=app_config.model_dump(mode="json"),
        llm=_redact_llm(llm_config.model_dump(mode="json")),
        database=deps.db_config.model_dump(mode="json") if deps.db_config else {},
        notifications=_redact_notifications(deps.notif_config.model_dump(mode="json") if deps.notif_config else {}),
        guardrails=deps.guardrails.model_dump(mode="json") if deps.guardrails else {},
        watch=deps.watch_config.model_dump(mode="json") if deps.watch_config else {},
        hosts=host_configs,
    )
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass. Some existing tests that imported from TOML-loading paths may need adjusting — fix any import errors.

- [ ] **Step 8: Run lint**

Run: `uv run ruff check src/squire/api/app.py src/squire/main.py src/squire/watch.py src/squire/agent.py src/squire/api/dependencies.py src/squire/api/routers/config.py`
Expected: Clean (no unused imports, etc.)

- [ ] **Step 9: Commit**

```bash
git add src/squire/api/app.py src/squire/api/dependencies.py src/squire/main.py src/squire/watch.py src/squire/agent.py src/squire/api/routers/config.py
git commit -m "refactor(hosts): replace TOML host loading with HostStore at all entry points"
```

---

### Task 6: CLI Host Commands

**Files:**
- Modify: `src/squire/cli.py`

- [ ] **Step 1: Add hosts subcommand group to CLI**

In `src/squire/cli.py`, add the following after the skills section (after line 530, before `if __name__`):

```python
# --- Host management ---

hosts_app = typer.Typer(name="hosts", help="Manage remote hosts.")
app.add_typer(hosts_app)


@hosts_app.command("list")
def hosts_list() -> None:
    """List all managed hosts."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            return await store.list_hosts(), await db.list_managed_hosts()
        finally:
            await db.close()

    configs, rows = asyncio.run(_run())

    if not configs:
        typer.echo("No managed hosts. Add one with: squire hosts add")
        return

    status_map = {r["name"]: r["status"] for r in rows}
    console = Console()
    table = Table(title="Managed Hosts")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Address", style="white")
    table.add_column("User", style="blue")
    table.add_column("Port", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Tags", style="yellow")

    for cfg in configs:
        status = status_map.get(cfg.name, "unknown")
        tags = ", ".join(cfg.tags) if cfg.tags else ""
        table.add_row(cfg.name, cfg.address, cfg.user, str(cfg.port), status, tags)

    console.print(table)


@hosts_app.command("add")
def hosts_add(
    name: Annotated[str, typer.Option("--name", "-n", help="Unique host alias")],
    address: Annotated[str, typer.Option("--address", "-a", help="Hostname or IP address")],
    user: Annotated[str, typer.Option("--user", "-u", help="SSH username")] = "root",
    port: Annotated[int, typer.Option("--port", "-p", help="SSH port")] = 22,
    tags: Annotated[str | None, typer.Option("--tags", "-t", help="Comma-separated tags")] = None,
    services: Annotated[str | None, typer.Option("--services", "-s", help="Comma-separated service names")] = None,
    service_root: Annotated[str, typer.Option("--service-root", help="Root directory for compose services")] = "/opt",
) -> None:
    """Enroll a new remote host."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    svc_list = [s.strip() for s in services.split(",") if s.strip()] if services else []

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            return await store.enroll(
                name=name,
                address=address,
                user=user,
                port=port,
                tags=tag_list,
                services=svc_list,
                service_root=service_root,
            )
        finally:
            await db.close()

    try:
        result = asyncio.run(_run())
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Generated SSH key for '{name}'.")
    if result.status == "active":
        typer.echo(result.message)
        typer.echo(f"Host '{name}' enrolled successfully.")
    else:
        typer.echo(result.message)
        typer.echo()
        typer.echo("Add this public key to ~/.ssh/authorized_keys on the remote host:")
        typer.echo()
        typer.echo(f"  {result.public_key}")
        typer.echo()
        typer.echo(f"Then run: squire hosts verify {name}")


@hosts_app.command("verify")
def hosts_verify(
    name: Annotated[str, typer.Argument(help="Name of the host to verify")],
) -> None:
    """Verify connectivity to a managed host."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            await store.load()
            return await store.verify(name)
        finally:
            await db.close()

    try:
        reachable = asyncio.run(_run())
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if reachable:
        typer.echo(f"Host '{name}' is reachable. Status updated to active.")
    else:
        typer.echo(f"Could not connect to '{name}'. Check that the public key is installed.")
        raise typer.Exit(1)


@hosts_app.command("remove")
def hosts_remove(
    name: Annotated[str, typer.Argument(help="Name of the host to remove")],
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Remove a managed host."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    if not yes and not typer.confirm(f"Remove host '{name}'? This deletes the SSH key."):
        raise typer.Abort()

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            await store.load()
            await store.remove(name)
        finally:
            await db.close()

    try:
        asyncio.run(_run())
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Host '{name}' removed.")
```

- [ ] **Step 2: Verify CLI commands register correctly**

Run: `uv run squire hosts --help`
Expected: Shows subcommands: list, add, verify, remove

Run: `uv run squire hosts list`
Expected: "No managed hosts. Add one with: squire hosts add"

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/squire/cli.py
git commit -m "feat(hosts): add CLI commands for host enrollment and management"
```

---

### Task 7: API Schemas and Endpoints

**Files:**
- Modify: `src/squire/api/schemas.py`
- Modify: `src/squire/api/routers/hosts.py`

- [ ] **Step 1: Add new API schemas**

In `src/squire/api/schemas.py`, add after the `HostInfo` class (after line 51):

```python
class HostCreate(BaseModel):
    name: str
    address: str
    user: str = "root"
    port: int = 22
    tags: list[str] = []
    services: list[str] = []
    service_root: str = "/opt"


class HostEnrollmentResponse(BaseModel):
    name: str
    status: str
    public_key: str
    message: str


class HostVerifyResponse(BaseModel):
    name: str
    reachable: bool
    message: str
```

Add `source` and `status` fields to the existing `HostInfo` class:

```python
class HostInfo(BaseModel):
    name: str
    address: str = ""
    user: str = ""
    port: int = 22
    tags: list[str] = []
    services: list[str] = []
    snapshot: HostSnapshot | None = None
    source: str = "managed"
    status: str = "active"
```

- [ ] **Step 2: Rewrite hosts router with full CRUD**

Replace the entire contents of `src/squire/api/routers/hosts.py`:

```python
"""Host management endpoints — list, enroll, verify, remove."""

import json

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_host_store, get_registry
from ..schemas import HostCreate, HostEnrollmentResponse, HostInfo, HostSnapshot, HostVerifyResponse
from ...system.keys import get_public_key

router = APIRouter()


@router.get("", response_model=list[HostInfo])
async def list_hosts(registry=Depends(get_registry), host_store=Depends(get_host_store)):
    """List all hosts (local + managed) with current status."""
    from ..app import get_latest_snapshot

    snapshot = await get_latest_snapshot()
    hosts = []

    # Local host
    snap_data = snapshot.get("local")
    hosts.append(
        HostInfo(
            name="local",
            address="localhost",
            source="local",
            status="active",
            snapshot=HostSnapshot(**snap_data) if snap_data else None,
        )
    )

    # Managed hosts from DB
    db_hosts = await host_store._db.list_managed_hosts()
    for row in db_hosts:
        cfg = host_store._row_to_config(row)
        snap_data = snapshot.get(cfg.name)
        hosts.append(
            HostInfo(
                name=cfg.name,
                address=cfg.address,
                user=cfg.user,
                port=cfg.port,
                tags=cfg.tags,
                services=cfg.services,
                source="managed",
                status=row["status"],
                snapshot=HostSnapshot(**snap_data) if snap_data else None,
            )
        )

    return hosts


@router.get("/{name}", response_model=HostInfo)
async def host_detail(name: str, registry=Depends(get_registry), host_store=Depends(get_host_store)):
    """Host detail with config and latest snapshot."""
    from ..app import get_latest_snapshot

    snapshot = await get_latest_snapshot()

    if name == "local":
        snap_data = snapshot.get("local")
        return HostInfo(
            name="local",
            address="localhost",
            source="local",
            status="active",
            snapshot=HostSnapshot(**snap_data) if snap_data else None,
        )

    host = await host_store.get_host(name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Host '{name}' not found")

    row = await host_store._db.get_managed_host(name)
    snap_data = snapshot.get(name)

    return HostInfo(
        name=host.name,
        address=host.address,
        user=host.user,
        port=host.port,
        tags=host.tags,
        services=host.services,
        source="managed",
        status=row["status"] if row else "active",
        snapshot=HostSnapshot(**snap_data) if snap_data else None,
    )


@router.post("", response_model=HostEnrollmentResponse, status_code=201)
async def enroll_host(body: HostCreate, host_store=Depends(get_host_store)):
    """Enroll a new managed host."""
    try:
        result = await host_store.enroll(
            name=body.name,
            address=body.address,
            user=body.user,
            port=body.port,
            tags=body.tags,
            services=body.services,
            service_root=body.service_root,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.delete("/{name}", status_code=204)
async def remove_host(name: str, host_store=Depends(get_host_store)):
    """Remove a managed host."""
    if name == "local":
        raise HTTPException(status_code=400, detail="Cannot remove the local host")
    try:
        await host_store.remove(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{name}/verify", response_model=HostVerifyResponse)
async def verify_host(name: str, host_store=Depends(get_host_store)):
    """Verify connectivity to a managed host."""
    try:
        reachable = await host_store.verify(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return HostVerifyResponse(
        name=name,
        reachable=reachable,
        message="Host is reachable." if reachable else "Could not connect.",
    )


@router.get("/{name}/public-key")
async def get_host_public_key(name: str, host_store=Depends(get_host_store)):
    """Get the public key for a managed host."""
    host = await host_store.get_host(name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Host '{name}' not found")
    pub_key = get_public_key(name)
    if pub_key is None:
        raise HTTPException(status_code=404, detail=f"No public key found for host '{name}'")
    return {"name": name, "public_key": pub_key}
```

- [ ] **Step 3: Run lint**

Run: `uv run ruff check src/squire/api/routers/hosts.py src/squire/api/schemas.py`
Expected: Clean

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/squire/api/schemas.py src/squire/api/routers/hosts.py
git commit -m "feat(hosts): add enrollment API endpoints and schemas"
```

---

### Task 8: Web UI — Types and Enrollment Form

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/app/hosts/page.tsx`

- [ ] **Step 1: Update TypeScript types**

In `web/src/lib/types.ts`, update the `HostInfo` interface (replace lines 27-35):

```typescript
export interface HostInfo {
  name: string;
  address: string;
  user: string;
  port: number;
  tags: string[];
  services: string[];
  snapshot: HostSnapshot | null;
  source: string;
  status: string;
}

export interface HostCreate {
  name: string;
  address: string;
  user: string;
  port: number;
  tags: string[];
  services: string[];
  service_root: string;
}

export interface HostEnrollmentResponse {
  name: string;
  status: string;
  public_key: string;
  message: string;
}

export interface HostVerifyResponse {
  name: string;
  reachable: boolean;
  message: string;
}
```

- [ ] **Step 2: Rewrite hosts page with enrollment form, status badges, and remove/verify actions**

Replace the entire contents of `web/src/app/hosts/page.tsx`:

```tsx
"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR, { mutate } from "swr";
import Link from "next/link";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  HostInfo,
  HostEnrollmentResponse,
  HostVerifyResponse,
} from "@/lib/types";
import {
  ArrowLeft,
  Check,
  Copy,
  Loader2,
  Plus,
  Server,
  ShieldAlert,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";

function HostsSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-32" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "active") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Check className="h-3 w-3" />
        Active
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 border-amber-500 text-amber-600">
      <ShieldAlert className="h-3 w-3" />
      Pending Key
    </Badge>
  );
}

function AddHostDialog() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HostEnrollmentResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData(e.currentTarget);
    const tagsStr = (form.get("tags") as string) || "";
    const servicesStr = (form.get("services") as string) || "";

    try {
      const res = await apiPost<HostEnrollmentResponse>("/api/hosts", {
        name: form.get("name"),
        address: form.get("address"),
        user: form.get("user") || "root",
        port: Number(form.get("port")) || 22,
        tags: tagsStr
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        services: servicesStr
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        service_root: form.get("service_root") || "/opt",
      });
      setResult(res);
      mutate("/api/hosts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enrollment failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleClose = () => {
    setOpen(false);
    setResult(null);
    setError(null);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-1">
          <Plus className="h-4 w-4" />
          Add Host
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {result ? "Enrollment Result" : "Add Host"}
          </DialogTitle>
          <DialogDescription>
            {result
              ? "Review the enrollment result below."
              : "Enter the connection details for the remote host."}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <StatusBadge status={result.status} />
              <span className="text-sm">{result.message}</span>
            </div>
            {result.status === "pending_key" && (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  Add this public key to{" "}
                  <code className="text-xs">~/.ssh/authorized_keys</code> on
                  the remote host:
                </p>
                <div className="relative">
                  <pre className="bg-muted p-3 rounded text-xs break-all whitespace-pre-wrap">
                    {result.public_key}
                  </pre>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="absolute top-1 right-1 h-7 w-7"
                    onClick={() => handleCopy(result.public_key)}
                  >
                    {copied ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </Button>
                </div>
              </div>
            )}
            <Button onClick={handleClose} className="w-full">
              Done
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder="media-server"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="address">Address</Label>
                <Input
                  id="address"
                  name="address"
                  placeholder="10.0.0.5"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="user">User</Label>
                <Input
                  id="user"
                  name="user"
                  placeholder="root"
                  defaultValue="root"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="port">Port</Label>
                <Input
                  id="port"
                  name="port"
                  type="number"
                  placeholder="22"
                  defaultValue="22"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tags">Tags (comma-separated)</Label>
              <Input
                id="tags"
                name="tags"
                placeholder="production, docker"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="services">Services (comma-separated)</Label>
              <Input
                id="services"
                name="services"
                placeholder="nginx, postgres"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service_root">Service Root</Label>
              <Input
                id="service_root"
                name="service_root"
                placeholder="/opt"
                defaultValue="/opt"
              />
            </div>
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Enroll Host
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function HostDetail({ name }: { name: string }) {
  const { data: host, isLoading } = useSWR(`/api/hosts/${name}`, () =>
    apiGet<HostInfo>(`/api/hosts/${name}`)
  );
  const [verifying, setVerifying] = useState(false);
  const [removing, setRemoving] = useState(false);

  if (isLoading || !host) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    );
  }

  const isReachable = host.snapshot && !host.snapshot.error;

  const handleVerify = async () => {
    setVerifying(true);
    try {
      await apiPost<HostVerifyResponse>(`/api/hosts/${name}/verify`);
      mutate(`/api/hosts/${name}`);
      mutate("/api/hosts");
    } finally {
      setVerifying(false);
    }
  };

  const handleRemove = async () => {
    if (!confirm(`Remove host '${name}'? This deletes the SSH key.`)) return;
    setRemoving(true);
    try {
      await apiDelete(`/api/hosts/${name}`);
      mutate("/api/hosts");
      window.location.href = "/hosts";
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <Link href="/hosts">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-2xl">{host.name}</h1>
        {isReachable ? (
          <Badge variant="secondary" className="gap-1">
            <Wifi className="h-3 w-3" />
            Reachable
          </Badge>
        ) : (
          <Badge variant="destructive" className="gap-1">
            <WifiOff className="h-3 w-3" />
            Unreachable
          </Badge>
        )}
        <StatusBadge status={host.status} />
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Address</p>
              <p className="font-mono">
                {host.address}
                {host.port !== 22 && `:${host.port}`}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">User</p>
              <p className="font-mono">{host.user}</p>
            </div>
            {host.snapshot?.hostname && (
              <div>
                <p className="text-muted-foreground">Hostname</p>
                <p className="font-mono">{host.snapshot.hostname}</p>
              </div>
            )}
            {host.snapshot?.os_info && (
              <div>
                <p className="text-muted-foreground">OS</p>
                <p className="font-mono">{host.snapshot.os_info}</p>
              </div>
            )}
          </div>

          {host.services.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground mb-2">Services</p>
              <div className="flex flex-wrap gap-1">
                {host.services.map((svc) => (
                  <Badge key={svc} variant="outline">
                    {svc}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {host.tags.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground mb-2">Tags</p>
              <div className="flex flex-wrap gap-1">
                {host.tags.map((tag) => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {host.source === "managed" && (
            <div className="flex gap-2 pt-2 border-t">
              {host.status === "pending_key" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleVerify}
                  disabled={verifying}
                >
                  {verifying && (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  )}
                  Verify Connection
                </Button>
              )}
              <Button
                size="sm"
                variant="destructive"
                onClick={handleRemove}
                disabled={removing}
              >
                {removing ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <Trash2 className="h-3 w-3 mr-1" />
                )}
                Remove
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function HostList() {
  const { data: hosts, isLoading } = useSWR("/api/hosts", () =>
    apiGet<HostInfo[]>("/api/hosts")
  );

  if (isLoading || !hosts) {
    return <HostsSkeleton />;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl">Hosts</h1>
        <Badge variant="secondary">{hosts.length}</Badge>
        <div className="ml-auto">
          <AddHostDialog />
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Hosts that Squire can connect to. For live metrics, use Beszel or
        Grafana.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {hosts.map((host) => {
          const isReachable = host.snapshot && !host.snapshot.error;

          return (
            <Link key={host.name} href={`/hosts?name=${host.name}`}>
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Server className="h-4 w-4" />
                    {host.name}
                    <div className="ml-auto flex items-center gap-1">
                      <StatusBadge status={host.status} />
                      {isReachable ? (
                        <Wifi className="h-3 w-3 text-green-500" />
                      ) : (
                        <WifiOff className="h-3 w-3 text-destructive" />
                      )}
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-sm text-muted-foreground font-mono">
                    {host.user}@{host.address}
                    {host.port !== 22 && `:${host.port}`}
                  </p>
                  {host.services.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {host.services.map((svc) => (
                        <Badge
                          key={svc}
                          variant="outline"
                          className="text-xs"
                        >
                          {svc}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {host.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {host.tags.map((tag) => (
                        <Badge
                          key={tag}
                          variant="secondary"
                          className="text-xs"
                        >
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default function HostsPage() {
  return (
    <Suspense fallback={<HostsSkeleton />}>
      <HostsPageInner />
    </Suspense>
  );
}

function HostsPageInner() {
  const searchParams = useSearchParams();
  const name = searchParams.get("name");

  if (name) {
    return <HostDetail name={name} />;
  }

  return <HostList />;
}
```

- [ ] **Step 3: Build the frontend to check for TypeScript errors**

Run: `cd web && npm run build`
Expected: Build succeeds with no type errors

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/types.ts web/src/app/hosts/page.tsx
git commit -m "feat(hosts): add enrollment form, status badges, and host management to web UI"
```

---

### Task 9: Update CHANGELOG and Final Verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CHANGELOG**

Add a new entry under the `## [Unreleased]` section (or create one) at the top of `CHANGELOG.md`:

```markdown
### Added
- Host enrollment system — Squire generates dedicated SSH keys per host and manages the full lifecycle
- `squire hosts add` / `remove` / `list` / `verify` CLI commands
- Web UI host enrollment form with public key display for manual setup
- `POST /api/hosts`, `DELETE /api/hosts/{name}`, `POST /api/hosts/{name}/verify`, `GET /api/hosts/{name}/public-key` API endpoints
- `HostStore` service for centralized host management

### Changed
- Host configuration moved from TOML `[[hosts]]` to SQLite database (clean break — re-add hosts via CLI or web UI)
- `BackendRegistry` now supports runtime `add_host()` / `remove_host()` for hot-reload
- Hosts page shows enrollment status badges and management actions

### Removed
- TOML `[[hosts]]` configuration support — hosts are now managed via CLI and web UI
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 3: Run lint and format check**

Run: `uv run ruff check && uv run ruff format --check`
Expected: Clean

- [ ] **Step 4: Run web build**

Run: `cd web && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for host enrollment feature"
```
