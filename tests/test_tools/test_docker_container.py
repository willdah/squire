"""Tests for docker_container tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_container import docker_container

from ..conftest import MockRegistry


class MockRegistryWithResolve(MockRegistry):
    """MockRegistry extended with resolve_host_for_service() returning None."""

    def resolve_host_for_service(self, service: str) -> str | None:
        return None


@pytest.fixture
def container_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistryWithResolve(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestInspect:
    @pytest.mark.asyncio
    async def test_inspect_returns_container_info(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Id": "abc123", "Name": "/nginx"}]', stderr=""),
        )
        result = await docker_container(action="inspect", container="nginx")
        assert "abc123" in result

    @pytest.mark.asyncio
    async def test_inspect_error(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="No such container: ghost"),
        )
        result = await docker_container(action="inspect", container="ghost")
        assert "Error" in result


class TestStart:
    @pytest.mark.asyncio
    async def test_start_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="start", container="nginx")
        assert "nginx" in result


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="stop", container="nginx")
        assert "nginx" in result


class TestRestart:
    @pytest.mark.asyncio
    async def test_restart_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="restart", container="nginx")
        assert "nginx" in result


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="remove", container="nginx")
        assert "nginx" in result

    @pytest.mark.asyncio
    async def test_remove_force(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="remove", container="nginx", force=True)
        assert "nginx" in result

    @pytest.mark.asyncio
    async def test_remove_error_container_running(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="container is running"),
        )
        result = await docker_container(action="remove", container="nginx")
        assert "Error" in result


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_container(action="destroy", container="nginx")
        assert "Invalid action" in result

    @pytest.mark.asyncio
    async def test_container_required(self, mock_backend, container_registry):
        result = await docker_container(action="inspect", container="")
        assert "container name" in result.lower()


class TestHostResolution:
    @pytest.mark.asyncio
    async def test_explicit_host(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Id": "abc"}]', stderr=""),
        )
        result = await docker_container(action="inspect", container="nginx", host="remote-server")
        assert "abc" in result
