"""docker_compose tool — read and manage Docker Compose stacks."""

from ._registry import get_registry

RISK_LEVEL = 3  # Moderate


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
            If not specified, uses the current directory.
        service: Optional specific service name to target.
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns the command output as text.
    """
    allowed_actions = {"ps", "config", "restart", "up", "down", "pull", "logs"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    backend = get_registry().get(host)
    cmd = ["docker", "compose"]

    if project_dir:
        cmd.extend(["-f", f"{project_dir}/docker-compose.yml"])

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
        return f"Error running 'docker compose {action}': {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker compose {action} completed successfully."
