"""read_config tool — read configuration files with path allowlist enforcement."""

import os

from ..config import PathsConfig
from ..system import LocalBackend

RISK_LEVEL = "read"

_backend = LocalBackend()
_paths_config = PathsConfig()


async def read_config(path: str, head: int | None = None) -> str:
    """Read a configuration file from the system.

    The file must be within one of the allowed directories configured in
    the paths allowlist. This prevents reading sensitive files outside
    approved locations.

    Args:
        path: Absolute path to the configuration file.
        head: Optional number of lines to return from the beginning of the file.

    Returns the file contents as text.
    """
    # Resolve to absolute path and normalize
    resolved = os.path.realpath(path)

    # Check allowlist
    allowlist = _paths_config.config_allowlist
    if allowlist:
        allowed = any(resolved.startswith(os.path.realpath(allowed_dir)) for allowed_dir in allowlist)
        if not allowed:
            return (
                f"Access denied: '{path}' is not within any allowed directory.\n"
                f"Allowed directories: {', '.join(allowlist)}"
            )

    try:
        content = await _backend.read_file(resolved)
    except FileNotFoundError:
        return f"File not found: {path}"
    except PermissionError:
        return f"Permission denied: {path}"

    if head is not None and head > 0:
        lines = content.split("\n")
        content = "\n".join(lines[:head])

    return content
