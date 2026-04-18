"""docker_logs tool — read container logs."""

from ._docker_hints import append_local_docker_error_hint
from ._effects import Effect
from ._registry import get_registry

RISK_LEVEL = 2  # Low
EFFECT: Effect = "read"


async def docker_logs(
    container: str,
    tail: int = 100,
    since: str | None = None,
    grep: str | None = None,
    host: str = "local",
) -> str:
    """Read logs from a Docker container.

    Args:
        container: Container name or ID.
        tail: Number of lines to return from the end (default 100).
        since: Only return logs since this timestamp (e.g., "1h", "2024-01-01T00:00:00").
        grep: Optional string to filter log lines (case-insensitive).
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns the log output as text.
    """
    registry = get_registry()

    # Auto-resolve host from container name when host is defaulted to "local"
    resolved_host = host
    if host == "local":
        matched = registry.resolve_host_for_service(container)
        if matched:
            resolved_host = matched

    backend = registry.get(resolved_host)
    cmd = ["docker", "logs", "--tail", str(tail)]

    if since:
        cmd.extend(["--since", since])

    cmd.append(container)

    result = await backend.run(cmd, timeout=30.0)

    if result.returncode != 0:
        err = f"Error reading logs for '{container}': {result.stderr}"
        return append_local_docker_error_hint(resolved_host, err)

    output = result.stdout + result.stderr  # docker logs writes to stderr too

    if grep:
        lines = output.split("\n")
        filtered = [line for line in lines if grep.lower() in line.lower()]
        output = "\n".join(filtered)
        if not output:
            return f"No log lines matching '{grep}' in the last {tail} lines of '{container}'."

    return output.strip() if output.strip() else f"No logs found for '{container}'."
