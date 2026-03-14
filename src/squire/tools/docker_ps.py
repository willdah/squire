"""docker_ps tool — list Docker containers with status."""

from ._registry import get_registry

RISK_LEVEL = 1  # Info


async def docker_ps(all_containers: bool = True, format: str = "table", host: str = "local") -> str:
    """List Docker containers with their status, image, ports, and names.

    Args:
        all_containers: Include stopped containers (default True).
        format: Output format - "table" for human-readable, "json" for structured data.
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns container listing as text or JSON.
    """
    backend = get_registry().get(host)
    cmd = ["docker", "ps"]
    if all_containers:
        cmd.append("-a")

    if format == "json":
        cmd.extend(["--format", "{{json .}}"])
    else:
        cmd.extend(
            [
                "--format",
                "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.State}}\t{{.Ports}}",
            ]
        )

    result = await backend.run(cmd)

    if result.returncode != 0:
        return f"Error running docker ps: {result.stderr}"

    return result.stdout.strip() if result.stdout.strip() else "No containers found."
