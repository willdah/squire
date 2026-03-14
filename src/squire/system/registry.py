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

    def get_config(self, host: str) -> HostConfig | None:
        """Return the HostConfig for the given host name, or None if not found."""
        return self._hosts.get(host)

    def resolve_host_for_service(self, service: str) -> str | None:
        """Find the host that owns a service, if exactly one match exists.

        Returns the host name, or None if the service is not registered
        or is ambiguous (on multiple hosts).
        """
        matches = [name for name, cfg in self._hosts.items() if service in cfg.services]
        return matches[0] if len(matches) == 1 else None

    async def close_all(self) -> None:
        """Close all backend connections."""
        for backend in self._backends.values():
            await backend.close()
