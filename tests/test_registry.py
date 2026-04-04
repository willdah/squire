"""Tests for BackendRegistry."""

import pytest

from squire.config.hosts import HostConfig
from squire.system.local import LocalBackend
from squire.system.registry import BackendRegistry


class TestBackendRegistry:
    def test_local_always_available(self):
        registry = BackendRegistry()
        backend = registry.get("local")
        assert isinstance(backend, LocalBackend)

    def test_host_names_local_only(self):
        registry = BackendRegistry()
        assert registry.host_names == ["local"]

    def test_host_names_with_hosts(self):
        hosts = [
            HostConfig(name="server-a", address="10.0.0.1"),
            HostConfig(name="server-b", address="10.0.0.2"),
        ]
        registry = BackendRegistry(hosts)
        assert registry.host_names == ["local", "server-a", "server-b"]

    def test_unknown_host_raises(self):
        registry = BackendRegistry()
        with pytest.raises(ValueError, match="Unknown host"):
            registry.get("nonexistent")

    def test_host_configs_property(self):
        hosts = [HostConfig(name="nas", address="10.0.0.5", user="admin", port=2222)]
        registry = BackendRegistry(hosts)
        configs = registry.host_configs
        assert "nas" in configs
        assert configs["nas"].address == "10.0.0.5"
        assert configs["nas"].user == "admin"
        assert configs["nas"].port == 2222

    def test_local_backend_cached(self):
        registry = BackendRegistry()
        b1 = registry.get("local")
        b2 = registry.get("local")
        assert b1 is b2

    def test_ssh_backend_cached(self):
        hosts = [HostConfig(name="srv", address="10.0.0.1")]
        registry = BackendRegistry(hosts)
        b1 = registry.get("srv")
        b2 = registry.get("srv")
        assert b1 is b2

    def test_resolve_host_for_service_unique(self):
        hosts = [
            HostConfig(name="apps", address="10.0.0.1", services=["syncthing", "ollama"]),
            HostConfig(name="core", address="10.0.0.2", services=["caddy"]),
        ]
        registry = BackendRegistry(hosts)
        assert registry.resolve_host_for_service("syncthing") == "apps"
        assert registry.resolve_host_for_service("caddy") == "core"

    def test_resolve_host_for_service_ambiguous(self):
        hosts = [
            HostConfig(name="a", address="10.0.0.1", services=["nginx"]),
            HostConfig(name="b", address="10.0.0.2", services=["nginx"]),
        ]
        registry = BackendRegistry(hosts)
        assert registry.resolve_host_for_service("nginx") is None

    def test_resolve_host_for_service_not_found(self):
        hosts = [HostConfig(name="a", address="10.0.0.1", services=["syncthing"])]
        registry = BackendRegistry(hosts)
        assert registry.resolve_host_for_service("unknown") is None

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
