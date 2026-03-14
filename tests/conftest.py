"""Shared test fixtures for Renew tests."""

from pathlib import Path

import pytest
import pytest_asyncio

from renew.database.service import DatabaseService
from renew.system.backend import CommandResult


class MockBackend:
    """A mock SystemBackend that returns canned responses.

    Register responses with `set_response(cmd, result)` before calling tools.
    """

    def __init__(self):
        self._responses: dict[str, CommandResult] = {}
        self._files: dict[str, str] = {}

    def set_response(self, cmd_prefix: str, result: CommandResult) -> None:
        """Register a canned response for a command prefix (e.g. 'docker')."""
        self._responses[cmd_prefix] = result

    def set_file(self, path: str, content: str) -> None:
        """Register a canned file content."""
        self._files[path] = content

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> CommandResult:
        # Match by first command token
        key = cmd[0] if cmd else ""
        if key in self._responses:
            return self._responses[key]
        # Match by full command string
        full = " ".join(cmd)
        for prefix, result in self._responses.items():
            if full.startswith(prefix):
                return result
        return CommandResult(returncode=1, stdout="", stderr=f"mock: no response for {cmd}")

    async def read_file(self, path: str) -> str:
        if path in self._files:
            return self._files[path]
        raise FileNotFoundError(path)

    async def write_file(self, path: str, content: str) -> None:
        self._files[path] = content


@pytest.fixture
def mock_backend():
    """Provide a fresh MockBackend instance."""
    return MockBackend()


@pytest_asyncio.fixture
async def db(tmp_path):
    """Provide a temporary in-memory DatabaseService."""
    db = DatabaseService(tmp_path / "test.db")
    yield db
    await db.close()
