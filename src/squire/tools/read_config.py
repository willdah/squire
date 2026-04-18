"""read_config tool — read configuration files with path guard enforcement."""

import os
import posixpath

from ._effects import Effect
from ._registry import get_guardrails, get_registry

RISK_LEVEL = 2  # Low
EFFECT: Effect = "read"


async def read_config(path: str, head: int | None = None, host: str = "local") -> str:
    """Read a configuration file from the system.

    The file must be within one of the allowed directories configured in
    the paths guard. This prevents reading sensitive files outside
    approved locations.

    Args:
        path: Absolute path to the configuration file.
        head: Optional number of lines to return from the beginning of the file.
        host: Target host name (default "local"). Use a configured host name to query a remote machine.

    Returns the file contents as text.
    """
    guardrails = get_guardrails()
    allowlist = guardrails.config_paths
    if allowlist:
        if host == "local":
            # Local: resolve symlinks then check prefix
            resolved = os.path.realpath(path)
            allowed = any(resolved.startswith(os.path.realpath(d)) for d in allowlist)
        else:
            # Remote: normalize then string prefix match (can't resolve remote symlinks)
            resolved = posixpath.normpath(path)
            allowed = any(resolved.startswith(posixpath.normpath(d)) for d in allowlist)

        if not allowed:
            return (
                f"Access denied: '{path}' is not within any allowed directory.\n"
                f"Allowed directories: {', '.join(allowlist)}"
            )
    else:
        resolved = path if host != "local" else os.path.realpath(path)

    backend = get_registry().get(host)
    try:
        content = await backend.read_file(resolved)
    except FileNotFoundError:
        return f"File not found: {path}"
    except PermissionError:
        return f"Permission denied: {path}"

    if head is not None and head > 0:
        lines = content.split("\n")
        content = "\n".join(lines[:head])

    return content
