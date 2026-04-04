"""docker_container tool — manage individual container lifecycle."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_container:inspect": 1,
    "docker_container:start": 3,
    "docker_container:stop": 3,
    "docker_container:restart": 3,
    "docker_container:remove": 4,
}


async def docker_container(
    action: str,
    container: str,
    force: bool = False,
    host: str = "local",
) -> str:
    """Manage individual Docker container lifecycle.

    Args:
        action: The action to perform. One of:
            "inspect" - show detailed container configuration (read-only)
            "start" - start a stopped container
            "stop" - gracefully stop a running container
            "restart" - stop and start a container
            "remove" - delete a container (use force=True for running containers)
        container: Name or ID of the target container.
        force: Force the action (e.g., remove a running container). Default False.
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"inspect", "start", "stop", "restart", "remove"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    if not container:
        return "Error: container name is required."

    registry = get_registry()

    # Auto-resolve host from container/service name
    resolved_host = host
    if host == "local":
        matched = registry.resolve_host_for_service(container)
        if matched:
            resolved_host = matched

    backend = registry.get(resolved_host)

    if action == "inspect":
        cmd = ["docker", "inspect", container]
    elif action == "remove":
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container)
    else:
        cmd = ["docker", action, container]

    result = await backend.run(cmd, timeout=60.0)

    if result.returncode != 0:
        return f"Error running 'docker {action}' on '{container}': {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker {action} completed successfully for '{container}'."
