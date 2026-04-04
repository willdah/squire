"""Tests for docker_cleanup tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_cleanup import docker_cleanup

from ..conftest import MockRegistry


@pytest.fixture
def cleanup_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestDf:
    @pytest.mark.asyncio
    async def test_disk_usage(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="TYPE    TOTAL   ACTIVE  SIZE    RECLAIMABLE\nImages  5       2       1.2GB   800MB (66%)\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="df")
        assert "Images" in result


class TestPruneContainers:
    @pytest.mark.asyncio
    async def test_prune_containers(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Containers:\nabc123\ndef456\n\nTotal reclaimed space: 50MB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_containers")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestPruneImages:
    @pytest.mark.asyncio
    async def test_prune_images(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Images:\nsha256:abc123\n\nTotal reclaimed space: 500MB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_images")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestPruneVolumes:
    @pytest.mark.asyncio
    async def test_prune_volumes(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Volumes:\nvol1\n\nTotal reclaimed space: 1GB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_volumes")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestPruneAll:
    @pytest.mark.asyncio
    async def test_prune_all(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Containers:\nabc\nDeleted Images:\nsha256:def\n\nTotal reclaimed space: 2GB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_all")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestErrors:
    @pytest.mark.asyncio
    async def test_prune_error(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="permission denied"),
        )
        result = await docker_cleanup(action="prune_containers")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_cleanup(action="nuke")
        assert "Invalid action" in result
