"""Tool registry — collects all ADK tool functions and their risk levels.

Each tool module exports an async function and a RISK_LEVEL constant.
Tools are registered here for the agent and the risk gate callback.

Tool conventions:
- Every tool function is async, accepts an optional ``host`` parameter
  (default ``"local"``), and returns a ``str``.
- Errors are returned as descriptive strings (never raised) so the LLM
  can relay them to the user. Only use exceptions for truly unexpected
  failures that should surface as system errors.
- Each module sets a module-level ``RISK_LEVEL`` int (1–5) used by the
  risk gate callback to decide whether user approval is needed.
"""

from ._registry import get_db as get_db
from ._registry import get_notifier as get_notifier
from ._registry import get_registry as get_registry
from ._registry import set_db as set_db
from ._registry import set_notifier as set_notifier
from ._registry import set_registry as set_registry
from ._safe import safe_tool
from .docker_compose import RISK_LEVEL as _dc_risk
from .docker_compose import docker_compose
from .docker_logs import RISK_LEVEL as _dl_risk
from .docker_logs import docker_logs
from .docker_ps import RISK_LEVEL as _dp_risk
from .docker_ps import docker_ps
from .journalctl import RISK_LEVEL as _jctl_risk
from .journalctl import journalctl
from .network_info import RISK_LEVEL as _ni_risk
from .network_info import network_info
from .read_config import RISK_LEVEL as _rc_risk
from .read_config import read_config
from .run_command import RISK_LEVEL as _runcmd_risk
from .run_command import run_command
from .system_info import RISK_LEVEL as _si_risk
from .system_info import system_info
from .systemctl import RISK_LEVEL as _sctl_risk
from .systemctl import systemctl

ALL_TOOLS = [
    safe_tool(system_info),
    safe_tool(network_info),
    safe_tool(docker_ps),
    safe_tool(docker_logs),
    safe_tool(docker_compose),
    safe_tool(read_config),
    safe_tool(journalctl),
    safe_tool(systemctl),
    safe_tool(run_command),
]

TOOL_RISK_LEVELS: dict[str, int] = {
    "system_info": _si_risk,
    "network_info": _ni_risk,
    "docker_ps": _dp_risk,
    "docker_logs": _dl_risk,
    "docker_compose": _dc_risk,
    "read_config": _rc_risk,
    "journalctl": _jctl_risk,
    "systemctl": _sctl_risk,
    "run_command": _runcmd_risk,
}
