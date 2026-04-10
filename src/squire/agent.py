"""ADK agent entry point — exposes root_agent for `adk web` and `adk run`.

This module is discovered by the ADK CLI agent loader when running:
    adk web src/
    adk run src/ --agent squire

It creates the Squire agent with default configuration. The risk gate
runs without an ApprovalProvider, so NEEDS_APPROVAL results are auto-denied.
For interactive approval, use the web UI (`squire web`).
"""

import asyncio

from dotenv import load_dotenv

from .agents.squire_agent import create_squire_agent
from .callbacks.risk_gate import create_risk_gate
from .config import AppConfig, DatabaseConfig, LLMConfig, NotificationsConfig
from .database.service import DatabaseService
from .hosts.store import HostStore
from .notifications.webhook import WebhookDispatcher
from .system.registry import BackendRegistry
from .tools import TOOL_RISK_LEVELS, set_db, set_notifier, set_registry

load_dotenv()

# Set up service registry so tools can execute
_registry = BackendRegistry()
set_registry(_registry)

_db_config = DatabaseConfig()
_db = DatabaseService(_db_config.path)
set_db(_db)

_notif_config = NotificationsConfig()
_notifier = WebhookDispatcher(_notif_config)
set_notifier(_notifier)

# Load managed hosts from DB into the registry (sync wrapper for module-level init)
_host_store = HostStore(_db, _registry)
asyncio.get_event_loop().run_until_complete(_host_store.load())

_app_config = AppConfig()
_llm_config = LLMConfig()


if _app_config.multi_agent:
    root_agent = create_squire_agent(
        app_config=_app_config,
        llm_config=_llm_config,
        risk_gate_factory=create_risk_gate,
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
