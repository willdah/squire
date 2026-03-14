"""run_command tool — guarded shell execution with command allowlist/denylist."""

import shlex

from ..config import SecurityConfig
from ._registry import get_registry

RISK_LEVEL = 5  # Critical

_security_config: SecurityConfig | None = None


def _get_security_config() -> SecurityConfig:
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig()
    return _security_config


async def run_command(command: str, timeout: float = 30.0, host: str = "local") -> str:
    """Execute a shell command on the system.

    This is a guarded tool — the command is checked against an allowlist
    and denylist before execution. Denied commands are blocked entirely.
    Commands not on the allowlist require approval via the risk profile.

    Args:
        command: The shell command to execute (e.g., "ping -c 4 8.8.8.8").
        timeout: Maximum seconds to wait for the command to complete (default 30).
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns the command output (stdout + stderr) as text.
    """
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"Invalid command syntax: {e}"

    if not parts:
        return "Empty command."

    base_cmd = parts[0]

    security = _get_security_config()

    # Check denylist first
    if base_cmd in security.command_denylist:
        return f"DENIED: '{base_cmd}' is on the command denylist. Tell the user this command is not allowed."

    # Check allowlist
    if security.command_allowlist and base_cmd not in security.command_allowlist:
        return (
            f"DENIED: '{base_cmd}' is not on the command allowlist. Tell the user this command is not allowed.\n"
            f"Allowed commands: {', '.join(sorted(security.command_allowlist))}"
        )

    backend = get_registry().get(host)
    result = await backend.run(parts, timeout=min(timeout, 120.0))

    output_parts = []
    if result.stdout:
        output_parts.append(result.stdout)
    if result.stderr:
        output_parts.append(f"[stderr]\n{result.stderr}")
    if result.returncode != 0:
        output_parts.append(f"\n[exit code: {result.returncode}]")

    return "\n".join(output_parts).strip() if output_parts else "Command completed with no output."
