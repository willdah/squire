"""Tests for docker_network tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_network import docker_network

from ..conftest import MockRegistry


@pytest.fixture
def network_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestList:
    @pytest.mark.asyncio
    async def test_list_networks(self, mock_backend, network_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="ID   NAME   DRIVER   SCOPE\nabc1   my-net   bridge   local\n",
                stderr="",
            ),
        )
        result = await docker_network(action="list")
        assert "my-net" in result

    @pytest.mark.asyncio
    async def test_list_empty(self, mock_backend, network_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="", stderr=""),
        )
        result = await docker_network(action="list")
        assert "completed successfully" in result.lower()


class TestInspect:
    @pytest.mark.asyncio
    async def test_inspect_network(self, mock_backend, network_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Name": "my-net"}]', stderr=""),
        )
        result = await docker_network(action="inspect", network="my-net")
        assert "my-net" in result

    @pytest.mark.asyncio
    async def test_inspect_missing_network_param(self, mock_backend, network_registry):
        result = await docker_network(action="inspect")
        assert "network name is required" in result.lower()


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_network(action="create")
        assert "Invalid action" in result
