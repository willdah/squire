"""docker_image tool — manage Docker images."""

from ._docker_hints import append_local_docker_error_hint
from ._effects import Effect
from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_image:list": 1,
    "docker_image:inspect": 1,
    "docker_image:pull": 2,
    "docker_image:remove": 3,
}

EFFECTS: dict[str, Effect] = {
    "list": "read",
    "inspect": "read",
    "pull": "write",
    "remove": "write",
}


async def docker_image(
    action: str = "list",
    image: str = "",
    host: str = "local",
) -> str:
    """Manage Docker images.

    Args:
        action: The action to perform. One of:
            "list" - list all images with repository, tag, and size (read-only)
            "inspect" - show detailed image metadata (read-only)
            "pull" - pull or update an image from a registry
            "remove" - remove an image (fails if in use by a running container)
        image: Image reference (e.g., "nginx:latest"). Required for inspect, pull, and remove.
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"list", "inspect", "pull", "remove"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    if action in {"inspect", "pull", "remove"} and not image:
        return f"Error: image reference is required for '{action}'."

    backend = get_registry().get(host)

    if action == "list":
        cmd = [
            "docker",
            "images",
            "--format",
            "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}",
        ]
    elif action == "inspect":
        cmd = ["docker", "image", "inspect", image]
    elif action == "pull":
        cmd = ["docker", "pull", image]
    elif action == "remove":
        cmd = ["docker", "rmi", image]

    result = await backend.run(cmd, timeout=120.0)

    if result.returncode != 0:
        err = f"Error running 'docker image {action}'{f' for {image!r}' if image else ''}: {result.stderr}"
        return append_local_docker_error_hint(host, err)

    output = result.stdout.strip()
    return output if output else f"docker image {action} completed successfully."
