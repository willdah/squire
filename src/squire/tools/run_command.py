"""run_command tool — guarded shell execution with command allow/block lists."""

import shlex

from ..config import GuardrailsConfig
from ._registry import get_registry

RISK_LEVEL = 5  # Critical

_guardrails_config: GuardrailsConfig | None = None


def _get_guardrails_config() -> GuardrailsConfig:
    global _guardrails_config
    if _guardrails_config is None:
        _guardrails_config = GuardrailsConfig()
    return _guardrails_config


async def run_command(command: str, timeout: float = 30.0, host: str = "local") -> str:
    """Execute a shell command on the system.

    This is a guarded tool — the command is checked against an allowlist
    and blocklist before execution. Blocked commands are denied entirely.
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

    guardrails = _get_guardrails_config()

    # Check blocklist first
    if base_cmd in guardrails.commands_block:
        return f"DENIED: '{base_cmd}' is on the command blocklist. Tell the user this command is not allowed."

    # Check allowlist
    if guardrails.commands_allow and base_cmd not in guardrails.commands_allow:
        return (
            f"DENIED: '{base_cmd}' is not on the command allowlist. Tell the user this command is not allowed.\n"
            f"Allowed commands: {', '.join(sorted(guardrails.commands_allow))}"
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
