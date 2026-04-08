"""Tests for docker_volume tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_volume import docker_volume

from ..conftest import MockRegistry


@pytest.fixture
def volume_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestList:
    @pytest.mark.asyncio
    async def test_list_volumes(self, mock_backend, volume_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="DRIVER   NAME   SCOPE\nlocal   my-vol   local\n",
                stderr="",
            ),
        )
        result = await docker_volume(action="list")
        assert "my-vol" in result

    @pytest.mark.asyncio
    async def test_list_empty(self, mock_backend, volume_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="", stderr=""),
        )
        result = await docker_volume(action="list")
        assert "completed successfully" in result.lower()


class TestInspect:
    @pytest.mark.asyncio
    async def test_inspect_volume(self, mock_backend, volume_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Name": "my-vol"}]', stderr=""),
        )
        result = await docker_volume(action="inspect", volume="my-vol")
        assert "my-vol" in result

    @pytest.mark.asyncio
    async def test_inspect_missing_volume_param(self, mock_backend, volume_registry):
        result = await docker_volume(action="inspect")
        assert "volume name is required" in result.lower()


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_volume(action="create")
        assert "Invalid action" in result
