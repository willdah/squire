"""docker_ps tool — list Docker containers with status."""

from ..system import LocalBackend

RISK_LEVEL = "read"

_backend = LocalBackend()


async def docker_ps(all_containers: bool = True, format: str = "table") -> str:
    """List Docker containers with their status, image, ports, and names.

    Args:
        all_containers: Include stopped containers (default True).
        format: Output format - "table" for human-readable, "json" for structured data.

    Returns container listing as text or JSON.
    """
    cmd = ["docker", "ps"]
    if all_containers:
        cmd.append("-a")

    if format == "json":
        cmd.extend(["--format", "{{json .}}"])
    else:
        cmd.extend([
            "--format",
            "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.State}}\t{{.Ports}}",
        ])

    result = await _backend.run(cmd)

    if result.returncode != 0:
        return f"Error running docker ps: {result.stderr}"

    return result.stdout.strip() if result.stdout.strip() else "No containers found."
