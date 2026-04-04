"""docker_cleanup tool — prune unused Docker resources."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_cleanup:df": 1,
    "docker_cleanup:prune_containers": 3,
    "docker_cleanup:prune_images": 3,
    "docker_cleanup:prune_volumes": 4,
    "docker_cleanup:prune_all": 4,
}


async def docker_cleanup(
    action: str = "df",
    host: str = "local",
) -> str:
    """Prune unused Docker resources and check disk usage.

    Args:
        action: The cleanup action to perform. One of:
            "df" - show Docker disk usage breakdown (read-only)
            "prune_containers" - remove all stopped containers
            "prune_images" - remove dangling (unused) images
            "prune_volumes" - remove unused volumes (WARNING: may delete data)
            "prune_all" - system prune: containers, images, and networks (excludes volumes)
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"df", "prune_containers", "prune_images", "prune_volumes", "prune_all"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    backend = get_registry().get(host)

    if action == "df":
        cmd = ["docker", "system", "df"]
    elif action == "prune_containers":
        cmd = ["docker", "container", "prune", "-f"]
    elif action == "prune_images":
        cmd = ["docker", "image", "prune", "-f"]
    elif action == "prune_volumes":
        cmd = ["docker", "volume", "prune", "-f"]
    elif action == "prune_all":
        cmd = ["docker", "system", "prune", "-f"]

    result = await backend.run(cmd, timeout=120.0)

    if result.returncode != 0:
        return f"Error running 'docker {action}': {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker {action} completed successfully."
