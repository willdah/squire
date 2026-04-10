"""docker_network tool — manage Docker networks."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_network:list": 1,
    "docker_network:inspect": 1,
}


async def docker_network(
    action: str = "list",
    network: str = "",
    host: str = "local",
) -> str:
    """Manage Docker networks.

    Args:
        action: The action to perform. One of:
            "list" - list all networks with basic info (read-only)
            "inspect" - show detailed network metadata (read-only)
        network: Network name. Required for inspect.
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"list", "inspect"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    if action == "inspect" and not network:
        return f"Error: network name is required for '{action}'."

    backend = get_registry().get(host)

    if action == "list":
        cmd = [
            "docker",
            "network",
            "ls",
            "--format",
            "table {{.ID}}\t{{.Name}}\t{{.Driver}}\t{{.Scope}}",
        ]
    elif action == "inspect":
        cmd = ["docker", "network", "inspect", network]

    result = await backend.run(cmd, timeout=30.0)

    if result.returncode != 0:
        return f"Error running 'docker network {action}'{f' for {network!r}' if network else ''}: {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker network {action} completed successfully."
