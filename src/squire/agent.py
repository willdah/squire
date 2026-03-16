"""ADK agent entry point — exposes root_agent for `adk web` and `adk run`.

This module is discovered by the ADK CLI agent loader when running:
    adk web src/
    adk run src/ --agent squire

It creates the Squire agent with default configuration. The risk gate
runs without an ApprovalProvider, so NEEDS_APPROVAL results are auto-denied.
For interactive approval, use the TUI via `squire chat`.
"""

from dotenv import load_dotenv

from .agents.squire_agent import create_squire_agent
from .callbacks.risk_gate import create_risk_gate
from .config import AppConfig, DatabaseConfig, LLMConfig, NotificationsConfig
from .config.hosts import HostConfig
from .config.loader import get_list_section
from .database.service import DatabaseService
from .notifications.webhook import WebhookDispatcher
from .system.registry import BackendRegistry
from .tools import TOOL_RISK_LEVELS, set_db, set_notifier, set_registry

load_dotenv()

# Set up service registry so tools can execute
_host_dicts = get_list_section("hosts")
_hosts = [HostConfig(**h) for h in _host_dicts]
_registry = BackendRegistry(_hosts)
set_registry(_registry)

_db_config = DatabaseConfig()
_db = DatabaseService(_db_config.path)
set_db(_db)

_notif_config = NotificationsConfig()
_notifier = WebhookDispatcher(_notif_config)
set_notifier(_notifier)

_app_config = AppConfig()
_llm_config = LLMConfig()

def _make_risk_gate(tool_risk_levels: dict[str, int]):
    return create_risk_gate(tool_risk_levels=tool_risk_levels)


if _app_config.multi_agent:
    root_agent = create_squire_agent(
        app_config=_app_config,
        llm_config=_llm_config,
        risk_gate_factory=_make_risk_gate,
    )
else:
    _risk_gate_callback = create_risk_gate(
        tool_risk_levels=TOOL_RISK_LEVELS,
    )
    root_agent = create_squire_agent(
        app_config=_app_config,
        llm_config=_llm_config,
        before_tool_callback=_risk_gate_callback,
    )
