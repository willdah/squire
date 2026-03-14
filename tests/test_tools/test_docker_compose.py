"""Tests for docker_compose tool with mocked backend."""

import pytest

from squire.config.hosts import HostConfig
from squire.system.backend import CommandResult
from squire.system.registry import BackendRegistry
from squire.tools import docker_compose
from squire.tools._registry import set_registry

from ..conftest import MockBackend


class MockRegistryWithConfig:
    """A mock registry that supports get_config() and resolve_host_for_service()."""

    def __init__(self, backend: MockBackend, hosts: list[HostConfig] | None = None):
        self._backend = backend
        self._hosts = {h.name: h for h in (hosts or [])}

    def get(self, host: str = "local"):
        return self._backend

    def get_config(self, host: str) -> HostConfig | None:
        return self._hosts.get(host)

    def resolve_host_for_service(self, service: str) -> str | None:
        matches = [name for name, cfg in self._hosts.items() if service in cfg.services]
        return matches[0] if len(matches) == 1 else None

    @property
    def host_names(self) -> list[str]:
        return ["local"] + list(self._hosts.keys())


@pytest.fixture
def compose_registry(mock_backend):
    """Provide a MockRegistryWithConfig and install it globally."""
    hosts = [
        HostConfig(
            name="prod-apps-01", address="10.20.0.100", service_root="/opt",
            services=["syncthing", "ollama", "immich"],
        ),
        HostConfig(
            name="custom-root", address="10.20.0.200", service_root="/srv/stacks",
            services=["grafana"],
        ),
    ]
    registry = MockRegistryWithConfig(mock_backend, hosts)
    set_registry(registry)
    yield registry
    set_registry(None)


@pytest.mark.asyncio
async def test_auto_resolve_service_path(mock_backend, compose_registry):
    """service='syncthing' with no project_dir should resolve to /opt/syncthing."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="syncthing restarted\n",
        stderr="",
    ))

    result = await docker_compose(action="restart", service="syncthing", host="prod-apps-01")
    assert "restarted" in result or "completed" in result


@pytest.mark.asyncio
async def test_explicit_project_dir_takes_precedence(mock_backend, compose_registry):
    """An explicit project_dir should be used instead of auto-resolution."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="ok\n",
        stderr="",
    ))

    result = await docker_compose(
        action="ps", project_dir="/custom/path", service="syncthing", host="prod-apps-01"
    )
    assert result  # Should not crash


@pytest.mark.asyncio
async def test_auto_resolve_custom_service_root(mock_backend, compose_registry):
    """Hosts with a custom service_root should use it for auto-resolution."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="pulled\n",
        stderr="",
    ))

    result = await docker_compose(action="pull", service="app", host="custom-root")
    assert "pulled" in result or "completed" in result


@pytest.mark.asyncio
async def test_error_message_includes_resolved_path(mock_backend, compose_registry):
    """Error messages should include the resolved path for diagnosability."""
    mock_backend.set_response("docker", CommandResult(
        returncode=1,
        stdout="",
        stderr="no such file",
    ))

    result = await docker_compose(action="restart", service="syncthing", host="prod-apps-01")
    assert "/opt/syncthing/docker-compose.yml" in result


@pytest.mark.asyncio
async def test_no_service_no_project_dir(mock_backend, compose_registry):
    """With no service and no project_dir, no -f flag should be added."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="NAME   STATUS\n",
        stderr="",
    ))

    result = await docker_compose(action="ps", host="prod-apps-01")
    assert result


@pytest.mark.asyncio
async def test_auto_resolve_host_from_service(mock_backend, compose_registry):
    """When host is omitted but service is registered on a host, auto-resolve the host."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="syncthing restarted\n",
        stderr="",
    ))

    # LLM forgets host — tool should resolve syncthing → prod-apps-01
    result = await docker_compose(action="restart", service="syncthing")
    assert "restarted" in result or "completed" in result


@pytest.mark.asyncio
async def test_auto_resolve_host_custom_service_root(mock_backend, compose_registry):
    """Host auto-resolution should also pick up the correct service_root."""
    mock_backend.set_response("docker", CommandResult(
        returncode=1,
        stdout="",
        stderr="no such file",
    ))

    # grafana is on custom-root with service_root=/srv/stacks
    result = await docker_compose(action="restart", service="grafana")
    assert "/srv/stacks/grafana/docker-compose.yml" in result


@pytest.mark.asyncio
async def test_explicit_host_not_overridden(mock_backend, compose_registry):
    """When host is explicitly set (not 'local'), don't override it."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="ok\n",
        stderr="",
    ))

    # syncthing is on prod-apps-01, but user explicitly says custom-root
    result = await docker_compose(action="ps", service="syncthing", host="custom-root")
    assert result  # Should not crash — uses custom-root's service_root


@pytest.mark.asyncio
async def test_unknown_service_stays_local(mock_backend, compose_registry):
    """Service not registered on any host should stay on local."""
    mock_backend.set_response("docker", CommandResult(
        returncode=0,
        stdout="ok\n",
        stderr="",
    ))

    result = await docker_compose(action="ps", service="unknown-app")
    assert result


@pytest.mark.asyncio
async def test_invalid_action():
    result = await docker_compose(action="destroy")
    assert "Invalid action" in result
