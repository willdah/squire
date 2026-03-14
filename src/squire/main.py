"""Async orchestration — session setup, agent runner, TUI launch."""

import asyncio
import json
import logging

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agents import create_squire_agent
from .config import AppConfig, DatabaseConfig, LLMConfig, NotificationsConfig
from .database.service import DatabaseService
from .notifications.webhook import WebhookDispatcher
from .schemas.risk import RiskProfile
from .tools.docker_ps import docker_ps
from .tools.system_info import system_info
from .tui.app import SquireApp

# Load environment variables before instantiating settings
load_dotenv()


async def _collect_snapshot() -> dict:
    """Run system_info and docker_ps to build an initial snapshot.

    Returns a dict suitable for the system prompt and status panel.
    """
    snapshot = {}

    try:
        sys_raw = await system_info()
        sys_data = json.loads(sys_raw)
        snapshot["hostname"] = sys_data.get("hostname", "unknown")
        snapshot["os_info"] = sys_data.get("os", "")
        snapshot["cpu_percent"] = sys_data.get("cpu_percent", 0)
        snapshot["memory_total_mb"] = sys_data.get("memory_total_mb", 0)
        snapshot["memory_used_mb"] = sys_data.get("memory_used_mb", 0)
        snapshot["uptime"] = sys_data.get("uptime", "")
        snapshot["disk_usage_raw"] = sys_data.get("disk_usage", "")
    except Exception:
        snapshot["hostname"] = "unknown"

    try:
        containers_raw = await docker_ps(all_containers=True, format="json")
        containers = []
        for line in containers_raw.strip().split("\n"):
            line = line.strip()
            if line and line.startswith("{"):
                try:
                    c = json.loads(line)
                    containers.append({
                        "name": c.get("Names", ""),
                        "image": c.get("Image", ""),
                        "status": c.get("Status", ""),
                        "state": c.get("State", ""),
                        "ports": c.get("Ports", ""),
                    })
                except json.JSONDecodeError:
                    pass
        snapshot["containers"] = containers
    except Exception:
        snapshot["containers"] = []

    return snapshot


async def _background_snapshots(db: DatabaseService, interval_minutes: int, tui: SquireApp) -> None:
    """Periodically collect and persist system snapshots.

    Also updates the TUI status panel and ADK session state.
    """
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            snapshot = await _collect_snapshot()
            await db.save_snapshot(snapshot)
            # Update TUI status panel from main thread
            tui.call_from_thread(tui.update_status_snapshot, snapshot)
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

    # Initialize database and webhook dispatcher
    db = DatabaseService(db_config.path)
    notifier = WebhookDispatcher(notif_config)

    # Build the agent and ADK runner
    agent = create_squire_agent(app_config=app_config, llm_config=llm_config)
    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=adk_app)

    # Build the risk profile from config
    risk_profile = RiskProfile(
        name=app_config.risk_profile,
        allowed_tools=set(app_config.custom_allowed_tools),
        approval_tools=set(app_config.custom_approval_tools),
        denied_tools=set(app_config.custom_denied_tools),
    )

    # Collect initial system snapshot
    snapshot = await _collect_snapshot()
    await db.save_snapshot(snapshot)

    session_state = {
        "risk_profile": risk_profile.model_dump(),
        "risk_profile_name": app_config.risk_profile,
        "latest_snapshot": snapshot,
        "house": app_config.house,
        "squire_name": app_config.squire_name,
        "squire_profile": app_config.squire_profile,
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
    )

    # Start background snapshot task
    snapshot_task = asyncio.create_task(
        _background_snapshots(db, db_config.snapshot_interval_minutes, tui)
    )

    try:
        await tui.run_async()
    finally:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
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
