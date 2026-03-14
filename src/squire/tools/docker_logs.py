"""docker_logs tool — read container logs."""

from ..system import LocalBackend

RISK_LEVEL = "read"

_backend = LocalBackend()


async def docker_logs(
    container: str,
    tail: int = 100,
    since: str | None = None,
    grep: str | None = None,
) -> str:
    """Read logs from a Docker container.

    Args:
        container: Container name or ID.
        tail: Number of lines to return from the end (default 100).
        since: Only return logs since this timestamp (e.g., "1h", "2024-01-01T00:00:00").
        grep: Optional string to filter log lines (case-insensitive).

    Returns the log output as text.
    """
    cmd = ["docker", "logs", "--tail", str(tail)]

    if since:
        cmd.extend(["--since", since])

    cmd.append(container)

    result = await _backend.run(cmd, timeout=30.0)

    if result.returncode != 0:
        return f"Error reading logs for '{container}': {result.stderr}"

    output = result.stdout + result.stderr  # docker logs writes to stderr too

    if grep:
        lines = output.split("\n")
        filtered = [line for line in lines if grep.lower() in line.lower()]
        output = "\n".join(filtered)
        if not output:
            return f"No log lines matching '{grep}' in the last {tail} lines of '{container}'."

    return output.strip() if output.strip() else f"No logs found for '{container}'."
