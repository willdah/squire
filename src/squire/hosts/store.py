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
            append_cmd = f"cat >> ~/.ssh/authorized_keys << 'SQUIRE_EOF'\n{public_key}\nSQUIRE_EOF"
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

        if port == 22:
            host_entry = address
        else:
            host_entry = f"[{address}]:{port}"

        key_data = peer_host_key.export_public_key("openssh").decode().strip()
        line = f"{host_entry} {key_data}\n"

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
