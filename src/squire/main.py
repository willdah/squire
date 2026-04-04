"""Async orchestration — session setup, agent runner, TUI launch."""

import asyncio
import json
import logging
from collections.abc import Callable

from agent_risk_engine import RiskEvaluator, RuleGate
from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agents import create_squire_agent
from .callbacks.risk_gate import create_risk_gate
from .config import AppConfig, DatabaseConfig, GuardrailsConfig, LLMConfig, NotificationsConfig
from .database.service import DatabaseService
from .hosts.store import HostStore
from .notifications.webhook import WebhookDispatcher
from .system.registry import BackendRegistry
from .tools import TOOL_RISK_LEVELS, set_db, set_notifier, set_registry
from .tools.docker_ps import docker_ps
from .tools.system_info import system_info
from .tui.app import SquireApp
from .tui.approval_bridge import ApprovalBridge

# Load environment variables before instantiating settings
load_dotenv()


async def _collect_snapshot(host: str = "local") -> dict:
    """Run system_info and docker_ps to build a snapshot for a single host.

    Args:
        host: Target host name (default "local").

    Returns a dict suitable for the system prompt and status panel.
    """
    snapshot = {}

    try:
        sys_raw = await system_info(host=host)
        sys_data = json.loads(sys_raw)
        snapshot["hostname"] = sys_data.get("hostname", "unknown")
        snapshot["os_info"] = sys_data.get("os", "")
        snapshot["cpu_percent"] = sys_data.get("cpu_percent", 0)
        snapshot["memory_total_mb"] = sys_data.get("memory_total_mb", 0)
        snapshot["memory_used_mb"] = sys_data.get("memory_used_mb", 0)
        snapshot["uptime"] = sys_data.get("uptime", "")
        snapshot["disk_usage_raw"] = sys_data.get("disk_usage", "")
    except Exception:
        logging.getLogger(__name__).debug("Failed to collect system_info for %s", host, exc_info=True)
        snapshot["hostname"] = host if host != "local" else "unknown"

    try:
        containers_raw = await docker_ps(all_containers=True, format="json", host=host)
        containers = []
        for line in containers_raw.strip().split("\n"):
            line = line.strip()
            if line and line.startswith("{"):
                try:
                    c = json.loads(line)
                    containers.append(
                        {
                            "name": c.get("Names", ""),
                            "image": c.get("Image", ""),
                            "status": c.get("Status", ""),
                            "state": c.get("State", ""),
                            "ports": c.get("Ports", ""),
                        }
                    )
                except json.JSONDecodeError:
                    pass
        snapshot["containers"] = containers
    except Exception:
        logging.getLogger(__name__).debug("Failed to collect docker_ps for %s", host, exc_info=True)
        snapshot["containers"] = []

    return snapshot


async def _collect_all_snapshots(registry: BackendRegistry) -> dict[str, dict]:
    """Collect snapshots from all configured hosts in parallel.

    Returns a dict keyed by host name, where each value is a snapshot dict.
    Unreachable hosts get an error entry instead of raising.
    """

    async def _collect_one(host: str) -> tuple[str, dict]:
        try:
            return (host, await _collect_snapshot(host=host))
        except Exception:
            logging.getLogger(__name__).debug("Failed to collect snapshot for %s", host, exc_info=True)
            return (host, {"hostname": host, "error": "unreachable", "containers": []})

    tasks = [_collect_one(h) for h in registry.host_names]
    results = await asyncio.gather(*tasks)
    return dict(results)


async def _background_snapshots(
    db: DatabaseService,
    interval_minutes: int,
    registry: BackendRegistry,
    on_snapshot: Callable[[dict], None] | None = None,
) -> None:
    """Periodically collect and persist system snapshots.

    Args:
        db: Database service for persisting snapshots.
        interval_minutes: Interval between snapshot collections.
        registry: Backend registry for host access.
        on_snapshot: Optional callback invoked with the snapshot dict after collection.
            Used by the TUI to update the status panel.
    """
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            snapshot = await _collect_all_snapshots(registry)
            if "local" in snapshot:
                await db.save_snapshot(snapshot["local"])
            if on_snapshot is not None:
                on_snapshot(snapshot)
        except Exception:
            logging.getLogger(__name__).debug("Background snapshot failed", exc_info=True)


async def start_chat(resume_session_id: str | None = None) -> None:
    """Start a Squire chat session with the TUI.

    Args:
        resume_session_id: Optional session ID to resume a previous conversation.
    """
    app_config = AppConfig()
    llm_config = LLMConfig()
    db_config = DatabaseConfig()
    notif_config = NotificationsConfig()

    # Create backend registry (hosts loaded from DB below)
    registry = BackendRegistry()
    set_registry(registry)

    # Initialize database and webhook dispatcher
    db = DatabaseService(db_config.path)
    notifier = WebhookDispatcher(notif_config)
    set_db(db)
    set_notifier(notifier)

    # Load managed hosts from DB into the registry
    host_store = HostStore(db, registry)
    await host_store.load()

    # Build the approval provider
    approval_bridge = ApprovalBridge()

    # Build the agent — multi-agent mode uses a factory for per-agent risk gates
    def _make_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            approval_provider=approval_bridge,
        )

    if app_config.multi_agent:
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory=_make_risk_gate,
        )
    else:
        risk_gate_callback = create_risk_gate(
            tool_risk_levels=TOOL_RISK_LEVELS,
            approval_provider=approval_bridge,
        )
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            before_tool_callback=risk_gate_callback,
        )
    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=adk_app)

    # Build the risk evaluation pipeline
    guardrails = GuardrailsConfig()
    rule_gate = RuleGate(
        threshold=app_config.risk_tolerance,
        strict=app_config.risk_strict,
        allowed=set(guardrails.tools_allow),
        approve=set(guardrails.tools_require_approval),
        denied=set(guardrails.tools_deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate)

    # Collect initial system snapshots (all hosts in parallel)
    snapshot = await _collect_all_snapshots(registry)
    # Save the local snapshot to DB (primary host)
    if "local" in snapshot:
        await db.save_snapshot(snapshot["local"])

    session_state = {
        "risk_evaluator": risk_evaluator,
        "risk_tolerance": rule_gate.threshold,
        "latest_snapshot": snapshot,
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

    # Load prior messages if resuming
    prior_messages: list[dict] = []
    if resume_session_id:
        prior_messages = await db.get_messages(resume_session_id)

    # Create ADK session
    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
        session_id=resume_session_id,
    )

    # Replay prior messages as ADK events so the LLM has context
    if prior_messages:
        for msg in prior_messages:
            role = msg.get("role", "user")
            content_text = msg.get("content", "")
            if not content_text:
                continue
            author = "user" if role == "user" else agent.name
            event = Event(
                author=author,
                invocation_id=Event.new_id(),
                content=types.Content(
                    role=role,
                    parts=[types.Part(text=content_text)],
                ),
            )
            await runner.session_service.append_event(session, event)

    # Register session in our DB (no-op on resume thanks to INSERT OR REPLACE)
    await db.create_session(session.id)

    # Launch the TUI
    tui = SquireApp(
        agent_runner=runner,
        session=session,
        app_config=app_config,
        db=db,
        notifier=notifier,
        initial_snapshot=snapshot,
        prior_messages=prior_messages if prior_messages else None,
        approval_bridge=approval_bridge,
    )

    # Start background snapshot task with callback to update TUI
    def _on_snapshot(snap: dict) -> None:
        tui.call_from_thread(tui.update_status_snapshot, snap)

    snapshot_task = asyncio.create_task(
        _background_snapshots(db, db_config.snapshot_interval_minutes, registry, on_snapshot=_on_snapshot)
    )

    try:
        await tui.run_async()
    finally:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
        await registry.close_all()
        await notifier.close()
        await db.close()


def run_chat(resume_session_id: str | None = None) -> None:
    """Synchronous wrapper to start a chat session."""
    asyncio.run(start_chat(resume_session_id))


async def list_sessions() -> list[dict]:
    """List recent chat sessions from the database."""
    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)
    try:
        return await db.list_sessions()
    finally:
        await db.close()
