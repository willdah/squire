"""SystemBackend protocol — abstraction over command execution.

All tools execute commands through this interface rather than calling
subprocess directly. In v1, only LocalBackend exists. Future versions
can add SSHBackend or AgentBackend without changing any tool code.
"""

from typing import Protocol

from pydantic import BaseModel


class CommandResult(BaseModel):
    """Result of a command execution."""

    returncode: int
    stdout: str
    stderr: str


class SystemBackend(Protocol):
    """Protocol for executing commands on a target system."""

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> CommandResult: ...

    async def read_file(self, path: str) -> str: ...

    async def write_file(self, path: str, content: str) -> None: ...
