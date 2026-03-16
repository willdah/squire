"""Tool groupings for sub-agent scoping.

Each group defines the tools and their risk levels assigned to a specific
sub-agent domain. Used by agent factories to create scoped agents.
"""

from . import TOOL_RISK_LEVELS
from .docker_compose import docker_compose
from .docker_logs import docker_logs
from .docker_ps import docker_ps
from .journalctl import journalctl
from .network_info import network_info
from .read_config import read_config
from .run_command import run_command
from .system_info import system_info
from .systemctl import systemctl

# Monitor agent — read-only system observation
MONITOR_TOOLS = [system_info, network_info, docker_ps, journalctl, read_config]
MONITOR_TOOL_NAMES = {t.__name__ for t in MONITOR_TOOLS}
MONITOR_RISK_LEVELS = {k: v for k, v in TOOL_RISK_LEVELS.items() if k in MONITOR_TOOL_NAMES}

# Container agent — container lifecycle management
CONTAINER_TOOLS = [docker_logs, docker_compose]
CONTAINER_TOOL_NAMES = {t.__name__ for t in CONTAINER_TOOLS}
CONTAINER_RISK_LEVELS = {k: v for k, v in TOOL_RISK_LEVELS.items() if k in CONTAINER_TOOL_NAMES}

# Admin agent — system administration and command execution
ADMIN_TOOLS = [systemctl, run_command]
ADMIN_TOOL_NAMES = {t.__name__ for t in ADMIN_TOOLS}
ADMIN_RISK_LEVELS = {k: v for k, v in TOOL_RISK_LEVELS.items() if k in ADMIN_TOOL_NAMES}
