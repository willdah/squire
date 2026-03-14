"""BackendRegistry — creates and caches SystemBackend instances per host."""

from __future__ import annotations

from ..config.hosts import HostConfig
from .local import LocalBackend
from .ssh import SSHBackend


class BackendRegistry:
    """Maps host names to SystemBackend instances.

    'local' always resolves to a LocalBackend. Configured remote hosts
    get an SSHBackend created lazily on first access.
    """

    def __init__(self, hosts: list[HostConfig] | None = None) -> None:
        self._hosts = {h.name: h for h in (hosts or [])}
        self._backends: dict = {"local": LocalBackend()}

    def get(self, host: str = "local"):
        """Return the backend for the given host name.

        Raises:
            ValueError: If the host name is not configured.
        """
        if host in self._backends:
            return self._backends[host]

        if host not in self._hosts:
            available = ", ".join(self.host_names)
            raise ValueError(f"Unknown host: '{host}'. Available hosts: {available}")

        config = self._hosts[host]
        backend = SSHBackend(
            address=config.address,
            user=config.user,
            port=config.port,
            key_file=config.key_file,
        )
        self._backends[host] = backend
        return backend

    @property
    def host_names(self) -> list[str]:
        """All configured host names including 'local'."""
        return ["local"] + list(self._hosts.keys())

    @property
    def host_configs(self) -> dict[str, HostConfig]:
        """Configured remote hosts keyed by name."""
        return dict(self._hosts)

    async def close_all(self) -> None:
        """Close all SSH connections."""
        for backend in self._backends.values():
            if hasattr(backend, "close"):
                await backend.close()
