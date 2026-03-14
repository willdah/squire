"""LocalBackend — executes commands on the local machine via asyncio subprocess."""

import asyncio
from pathlib import Path

from .backend import CommandResult


class LocalBackend:
    """Execute commands locally using asyncio.create_subprocess_exec."""

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> CommandResult:
        """Run a command and return its output.

        Args:
            cmd: Command and arguments as a list.
            timeout: Maximum seconds to wait for command completion.

        Returns:
            CommandResult with returncode, stdout, and stderr.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
            )

        return CommandResult(
            returncode=proc.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )

    async def read_file(self, path: str) -> str:
        """Read a file's contents.

        Args:
            path: Absolute path to the file.

        Returns:
            File contents as a string.
        """
        return Path(path).read_text()

    async def write_file(self, path: str, content: str) -> None:
        """Write content to a file.

        Args:
            path: Absolute path to the file.
            content: Content to write.
        """
        Path(path).write_text(content)

    async def close(self) -> None:
        """No-op for local backend."""
