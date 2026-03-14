"""SSHBackend — executes commands on a remote host via asyncssh."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

import asyncssh

from .backend import CommandResult


class SSHBackend:
    """Execute commands on a remote host over SSH.

    Connections are created lazily on first use and reused for subsequent calls.
    """

    def __init__(
        self,
        address: str,
        user: str = "root",
        port: int = 22,
        key_file: str | None = None,
        strict_host_keys: bool = True,
    ) -> None:
        self._address = address
        self._user = user
        self._port = port
        self._key_file = key_file
        self._strict_host_keys = strict_host_keys
        self._conn: asyncssh.SSHClientConnection | None = None
        self._conn_loop: asyncio.AbstractEventLoop | None = None
        self._os_type: str | None = None

    @property
    def os_type(self) -> str:
        """Remote OS type (e.g. 'Linux', 'Darwin'). Defaults to 'Linux' until probed."""
        return self._os_type or "Linux"

    async def _ensure_connection(self) -> asyncssh.SSHClientConnection:
        """Return the cached connection, creating or reconnecting as needed.

        Connections are bound to the event loop they were created on.
        If the current loop differs (e.g. Textual worker thread), the
        cached connection is discarded and a new one is created.
        """
        current_loop = asyncio.get_running_loop()

        if self._conn is not None and self._conn_loop is not current_loop:
            # Connection belongs to a different event loop — can't reuse
            self._conn = None

        if self._conn is not None:
            # Check if connection is still alive
            try:
                self._conn.get_extra_info("peername")
                return self._conn
            except (OSError, asyncssh.ConnectionLost):
                self._conn = None

        known_hosts: str | None = None
        if self._strict_host_keys:
            # Use the user's known_hosts file
            known_hosts_path = Path.home() / ".ssh" / "known_hosts"
            known_hosts = str(known_hosts_path) if known_hosts_path.exists() else ()
        else:
            known_hosts = None

        connect_kwargs: dict = {
            "host": self._address,
            "port": self._port,
            "username": self._user,
            "known_hosts": known_hosts,
            "keepalive_interval": 30,
        }
        if self._key_file:
            connect_kwargs["client_keys"] = [str(Path(self._key_file).expanduser())]

        self._conn = await asyncssh.connect(**connect_kwargs)
        self._conn_loop = current_loop

        # Probe remote OS type
        if self._os_type is None:
            try:
                result = await self._conn.run("uname -s", check=False, timeout=5)
                self._os_type = result.stdout.strip() if result.stdout else "Linux"
            except Exception:
                self._os_type = "Linux"

        return self._conn

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> CommandResult:
        """Run a command on the remote host.

        Args:
            cmd: Command and arguments as a list.
            timeout: Maximum seconds to wait for command completion.

        Returns:
            CommandResult with returncode, stdout, and stderr.
        """
        try:
            conn = await self._ensure_connection()
        except Exception as exc:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"SSH connection failed ({self._address}): {exc}",
            )

        shell_cmd = shlex.join(cmd)

        try:
            result = await asyncio.wait_for(
                conn.run(shell_cmd, check=False),
                timeout=timeout,
            )
        except TimeoutError:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
            )
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError, OSError) as exc:
            self._conn = None
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"SSH connection error: {exc}",
            )

        return CommandResult(
            returncode=result.returncode or 0,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def read_file(self, path: str) -> str:
        """Read a file on the remote host.

        Uses cat for simplicity and consistency with the run() interface.
        """
        result = await self.run(["cat", path])
        if result.returncode != 0:
            if "No such file" in result.stderr:
                raise FileNotFoundError(path)
            if "Permission denied" in result.stderr:
                raise PermissionError(path)
            raise OSError(f"Failed to read {path}: {result.stderr}")
        return result.stdout

    async def write_file(self, path: str, content: str) -> None:
        """Write content to a file on the remote host via SFTP."""
        try:
            conn = await self._ensure_connection()
        except Exception as exc:
            raise OSError(f"SSH connection failed ({self._address}): {exc}") from exc
        async with conn.start_sftp_client() as sftp:
            async with sftp.open(path, "w") as f:
                await f.write(content)

    async def close(self) -> None:
        """Close the SSH connection if it belongs to the current event loop."""
        if self._conn is not None:
            current_loop = asyncio.get_running_loop()
            if self._conn_loop is current_loop:
                self._conn.close()
                await self._conn.wait_closed()
            self._conn = None
            self._conn_loop = None
