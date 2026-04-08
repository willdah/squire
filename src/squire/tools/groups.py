"""Tool groupings for sub-agent scoping.

Each group defines the tools and their risk levels assigned to a specific
sub-agent domain. Used by agent factories to create scoped agents.
"""

from . import TOOL_RISK_LEVELS
from ._safe import safe_tool
from .docker_cleanup import docker_cleanup
from .docker_compose import docker_compose
from .docker_container import docker_container
from .docker_image import docker_image
from .docker_logs import docker_logs
from .docker_network import docker_network
from .docker_ps import docker_ps
from .docker_volume import docker_volume
from .journalctl import journalctl
from .network_info import network_info
from .read_config import read_config
from .run_command import run_command
from .system_info import system_info
from .systemctl import systemctl

# Monitor agent — read-only system observation
MONITOR_TOOLS = [
    safe_tool(system_info),
    safe_tool(network_info),
    safe_tool(docker_ps),
    safe_tool(journalctl),
    safe_tool(read_config),
]
MONITOR_TOOL_NAMES = {t.__name__ for t in MONITOR_TOOLS}
MONITOR_RISK_LEVELS = {
    k: v for k, v in TOOL_RISK_LEVELS.items() if k in MONITOR_TOOL_NAMES or k.split(":")[0] in MONITOR_TOOL_NAMES
}

# Container agent — container lifecycle management
CONTAINER_TOOLS = [
    safe_tool(docker_logs),
    safe_tool(docker_compose),
    safe_tool(docker_container),
    safe_tool(docker_image),
    safe_tool(docker_cleanup),
    safe_tool(docker_volume),
    safe_tool(docker_network),
]
CONTAINER_TOOL_NAMES = {t.__name__ for t in CONTAINER_TOOLS}
CONTAINER_RISK_LEVELS = {
    k: v for k, v in TOOL_RISK_LEVELS.items() if k in CONTAINER_TOOL_NAMES or k.split(":")[0] in CONTAINER_TOOL_NAMES
}

# Admin agent — system administration and command execution
ADMIN_TOOLS = [safe_tool(systemctl), safe_tool(run_command)]
ADMIN_TOOL_NAMES = {t.__name__ for t in ADMIN_TOOLS}
ADMIN_RISK_LEVELS = {
    k: v for k, v in TOOL_RISK_LEVELS.items() if k in ADMIN_TOOL_NAMES or k.split(":")[0] in ADMIN_TOOL_NAMES
}
