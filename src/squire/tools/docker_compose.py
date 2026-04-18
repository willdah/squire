"""docker_compose tool — read and manage Docker Compose stacks."""

from ._docker_hints import append_local_docker_error_hint
from ._effects import Effect
from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_compose:ps": 1,
    "docker_compose:config": 1,
    "docker_compose:logs": 1,
    "docker_compose:pull": 2,
    "docker_compose:restart": 3,
    "docker_compose:up": 3,
    "docker_compose:down": 4,
}

EFFECTS: dict[str, Effect] = {
    "ps": "read",
    "config": "read",
    "logs": "read",
    "pull": "write",
    "restart": "write",
    "up": "write",
    "down": "write",
}


async def docker_compose(
    action: str = "ps",
    project_dir: str | None = None,
    service: str | None = None,
    host: str = "local",
) -> str:
    """Manage Docker Compose stacks.

    Args:
        action: The compose action to perform. One of:
            "ps" - list services and their status (read-only)
            "config" - show the resolved compose configuration (read-only)
            "restart" - restart a service or the entire stack
            "up" - start services
            "down" - stop and remove services
            "pull" - pull latest images
        project_dir: Path to the directory containing docker-compose.yml.
            If omitted, the compose file is resolved at `/opt/<service>/docker-compose.yml`
            (or `<service_root>/<service>/` if the host has a custom service_root).
        service: Optional specific service name to target.
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns the command output as text.
    """
    allowed_actions = {"ps", "config", "restart", "up", "down", "pull", "logs"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    registry = get_registry()

    # Auto-resolve host from service name when host is defaulted to "local"
    resolved_host = host
    if host == "local" and service:
        matched = registry.resolve_host_for_service(service)
        if matched:
            resolved_host = matched

    backend = registry.get(resolved_host)

    # Auto-resolve project_dir from service name and host config
    resolved_dir = project_dir
    if not resolved_dir and service:
        service_root = "/opt"
        host_config = registry.get_config(resolved_host)
        if host_config and host_config.service_root:
            service_root = host_config.service_root
        resolved_dir = f"{service_root}/{service}"

    cmd = ["docker", "compose"]

    if resolved_dir:
        cmd.extend(["-f", f"{resolved_dir}/docker-compose.yml"])

    cmd.append(action)

    # Add flags based on action
    if action == "up":
        cmd.append("-d")  # Always detached
    if action == "ps":
        cmd.append("--format")
        cmd.append("table")

    if service:
        cmd.append(service)

    result = await backend.run(cmd, timeout=120.0)

    if result.returncode != 0:
        path_info = f" (resolved path: {resolved_dir}/docker-compose.yml)" if resolved_dir else ""
        err = f"Error running 'docker compose {action}'{path_info}: {result.stderr}"
        return append_local_docker_error_hint(resolved_host, err)

    output = result.stdout.strip()
    return output if output else f"docker compose {action} completed successfully."
