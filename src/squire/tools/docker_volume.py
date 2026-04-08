"""docker_volume tool — manage Docker volumes."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_volume:list": 1,
    "docker_volume:inspect": 1,
}


async def docker_volume(
    action: str = "list",
    volume: str = "",
    host: str = "local",
) -> str:
    """Manage Docker volumes.

    Args:
        action: The action to perform. One of:
            "list" - list all volumes with basic info (read-only)
            "inspect" - show detailed volume metadata (read-only)
        volume: Volume name. Required for inspect.
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"list", "inspect"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    if action == "inspect" and not volume:
        return f"Error: volume name is required for '{action}'."

    backend = get_registry().get(host)

    if action == "list":
        cmd = [
            "docker",
            "volume",
            "ls",
            "--format",
            "table {{.Driver}}\t{{.Name}}\t{{.Scope}}",
        ]
    elif action == "inspect":
        cmd = ["docker", "volume", "inspect", volume]

    result = await backend.run(cmd, timeout=30.0)

    if result.returncode != 0:
        return f"Error running 'docker volume {action}'{f' for {volume!r}' if volume else ''}: {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker volume {action} completed successfully."
