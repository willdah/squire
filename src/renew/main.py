"""Async orchestration — session setup, agent runner, TUI launch."""

import asyncio
import json

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.runners import InMemoryRunner

from .agents import create_renew_agent
from .config import AppConfig, LLMConfig
from .schemas.risk import RiskProfile
from .tools.system_info import system_info
from .tools.docker_ps import docker_ps
from .tui.app import RenewApp

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
        # Parse JSON lines from docker ps
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


async def start_chat(resume_session_id: str | None = None) -> None:
    """Start a Renew chat session with the TUI.

    Args:
        resume_session_id: Optional session ID to resume a previous conversation.
    """
    app_config = AppConfig()
    llm_config = LLMConfig()

    # Build the agent and ADK runner
    agent = create_renew_agent(app_config=app_config, llm_config=llm_config)
    app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=app)

    # Build the risk profile from config
    risk_profile = RiskProfile(
        name=app_config.risk_profile,
        allowed_tools=set(app_config.custom_allowed_tools),
        approval_tools=set(app_config.custom_approval_tools),
        denied_tools=set(app_config.custom_denied_tools),
    )

    # Collect initial system snapshot
    snapshot = await _collect_snapshot()

    # Create a new session with initial state
    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state={
            "risk_profile": risk_profile.model_dump(),
            "risk_profile_name": app_config.risk_profile,
            "latest_snapshot": snapshot,
        },
    )

    # Launch the TUI
    tui = RenewApp(
        agent_runner=runner,
        session=session,
        app_config=app_config,
        initial_snapshot=snapshot,
    )
    await tui.run_async()


def run_chat(resume_session_id: str | None = None) -> None:
    """Synchronous wrapper to start a chat session."""
    asyncio.run(start_chat(resume_session_id))
