"""journalctl tool — read systemd journal logs."""

from ._effects import Effect
from ._registry import get_registry

RISK_LEVEL = 2  # Low
EFFECT: Effect = "read"


async def journalctl(
    unit: str | None = None,
    lines: int = 50,
    since: str | None = None,
    priority: str | None = None,
    grep: str | None = None,
    host: str = "local",
) -> str:
    """Read systemd journal logs.

    Args:
        unit: Filter by systemd unit name (e.g., "nginx", "docker", "sshd").
        lines: Number of recent log lines to return (default 50).
        since: Only show entries since this time (e.g., "1 hour ago", "today", "2024-01-01").
        priority: Filter by priority level (e.g., "err", "warning", "info").
        grep: Filter log lines containing this string.
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns journal log output as text.
    """
    backend = get_registry().get(host)
    cmd = ["journalctl", "--no-pager", "-n", str(lines)]

    if unit:
        cmd.extend(["-u", unit])

    if since:
        cmd.extend(["--since", since])

    if priority:
        cmd.extend(["-p", priority])

    if grep:
        cmd.extend(["-g", grep])

    result = await backend.run(cmd, timeout=30.0)

    if result.returncode != 0:
        # journalctl may not be available on macOS
        if "not found" in result.stderr.lower() or "No such file" in result.stderr:
            return "journalctl is not available on this system (requires systemd)."
        return f"Error reading journal: {result.stderr}"

    return result.stdout.strip() if result.stdout.strip() else "No journal entries found matching the criteria."
