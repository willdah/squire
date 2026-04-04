"""Tests for docker_image tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_image import docker_image

from ..conftest import MockRegistry


@pytest.fixture
def image_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestList:
    @pytest.mark.asyncio
    async def test_list_images(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="REPOSITORY   TAG   IMAGE ID   SIZE\nnginx   latest   abc123   150MB\n",
                stderr="",
            ),
        )
        result = await docker_image(action="list")
        assert "nginx" in result

    @pytest.mark.asyncio
    async def test_list_empty(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="", stderr=""),
        )
        result = await docker_image(action="list")
        assert "no images" in result.lower() or "completed" in result.lower()


class TestInspect:
    @pytest.mark.asyncio
    async def test_inspect_image(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Id": "sha256:abc123"}]', stderr=""),
        )
        result = await docker_image(action="inspect", image="nginx:latest")
        assert "abc123" in result

    @pytest.mark.asyncio
    async def test_inspect_missing_image_param(self, mock_backend, image_registry):
        result = await docker_image(action="inspect")
        assert "image" in result.lower()


class TestPull:
    @pytest.mark.asyncio
    async def test_pull_image(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="latest: Pulling from library/nginx\nDigest: sha256:abc\n", stderr=""),
        )
        result = await docker_image(action="pull", image="nginx:latest")
        assert "nginx" in result or "Pulling" in result

    @pytest.mark.asyncio
    async def test_pull_missing_image_param(self, mock_backend, image_registry):
        result = await docker_image(action="pull")
        assert "image" in result.lower()

    @pytest.mark.asyncio
    async def test_pull_error(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="pull access denied"),
        )
        result = await docker_image(action="pull", image="private/image")
        assert "Error" in result


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_image(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="Untagged: nginx:latest\nDeleted: sha256:abc\n", stderr=""),
        )
        result = await docker_image(action="remove", image="nginx:latest")
        assert "Untagged" in result or "Deleted" in result

    @pytest.mark.asyncio
    async def test_remove_image_in_use(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="image is being used by running container"),
        )
        result = await docker_image(action="remove", image="nginx:latest")
        assert "Error" in result


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_image(action="build")
        assert "Invalid action" in result
