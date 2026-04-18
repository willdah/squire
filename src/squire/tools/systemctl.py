"""systemctl tool — manage systemd services."""

from ._effects import Effect
from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "systemctl:status": 1,
    "systemctl:is-active": 1,
    "systemctl:is-enabled": 1,
    "systemctl:start": 3,
    "systemctl:restart": 3,
    "systemctl:stop": 4,
}

EFFECTS: dict[str, Effect] = {
    "status": "read",
    "is-active": "read",
    "is-enabled": "read",
    "start": "write",
    "restart": "write",
    "stop": "write",
}


async def systemctl(
    action: str,
    unit: str,
    host: str = "local",
) -> str:
    """Manage systemd services (e.g. Caddy on prod-core-01).

    Args:
        action: The systemctl action to perform. One of:
            "status" - show service status (read-only)
            "is-active" - check if the service is active (read-only)
            "is-enabled" - check if the service is enabled (read-only)
            "restart" - restart the service
            "start" - start the service
            "stop" - stop the service
        unit: The systemd unit name (e.g. "caddy", "nginx", "docker").
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns the command output as text.
    """
    allowed_actions = {"status", "restart", "start", "stop", "is-active", "is-enabled"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    backend = get_registry().get(host)
    cmd = ["systemctl"]

    if action == "status":
        cmd.append("--no-pager")

    cmd.extend([action, unit])

    result = await backend.run(cmd, timeout=30.0)

    if result.returncode != 0:
        # systemctl status returns exit code 3 for inactive services — still useful output
        if action == "status" and result.stdout.strip():
            return result.stdout.strip()
        if "not found" in result.stderr.lower() or "No such file" in result.stderr:
            return "systemctl is not available on this system (requires systemd)."
        return f"Error running 'systemctl {action} {unit}': {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"systemctl {action} {unit} completed successfully."
