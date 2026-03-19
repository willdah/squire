"""Autonomous watch mode — headless monitoring loop.

Runs Squire without a TUI, periodically injecting a check-in prompt and
letting the agent reason about system state. Tools above the risk threshold
are denied outright; notifications are dispatched for actions and blocks.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import UTC, datetime

from agent_risk_engine import CallTracker, RiskEvaluator, RuleGate
from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agents.squire_agent import create_squire_agent
from .callbacks.risk_gate import create_risk_gate
from .config import (
    AppConfig,
    DatabaseConfig,
    GuardrailsConfig,
    LLMConfig,
    NotificationsConfig,
    WatchConfig,
)
from .config.hosts import HostConfig
from .config.loader import get_list_section
from .database.service import DatabaseService
from .main import _collect_all_snapshots
from .notifications.webhook import WebhookDispatcher
from .system.registry import BackendRegistry
from .tools import TOOL_RISK_LEVELS, set_db, set_notifier, set_registry

load_dotenv()

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure structured logging for watch mode to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger("squire")
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def start_watch() -> None:
    """Start the autonomous watch loop."""
    _configure_logging()

    app_config = AppConfig()
    llm_config = LLMConfig()
    db_config = DatabaseConfig()
    notif_config = NotificationsConfig()
    watch_config = WatchConfig()

    # Load host configuration and create backend registry
    host_dicts = get_list_section("hosts")
    hosts = [HostConfig(**h) for h in host_dicts]
    registry = BackendRegistry(hosts)
    set_registry(registry)

    # Initialize database and webhook dispatcher
    db = DatabaseService(db_config.path)
    notifier = WebhookDispatcher(notif_config)
    set_db(db)
    set_notifier(notifier)

    # Build the risk evaluation pipeline with CallTracker for loop detection
    guardrails = GuardrailsConfig()
    call_tracker = CallTracker()
    watch_tolerance = guardrails.watch_tolerance or app_config.risk_tolerance
    rule_gate = RuleGate(
        threshold=watch_tolerance,
        strict=True,  # Always strict in watch mode — deny, don't prompt
        allowed_tools=set(guardrails.tools_allow) | set(guardrails.watch_tools_allow),
        # tools_require_approval intentionally omitted — watch mode has no approval provider
        denied_tools=set(guardrails.tools_deny) | set(guardrails.watch_tools_deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate, state_monitor=call_tracker)

    # Build the agent with headless risk gate
    block_notifier = notifier if watch_config.notify_on_blocked else None

    def _make_headless_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            headless=True,
            notifier=block_notifier,
        )

    if app_config.multi_agent:
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory=_make_headless_risk_gate,
        )
    else:
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            before_tool_callback=_make_headless_risk_gate(TOOL_RISK_LEVELS),
        )

    # Create ADK runner
    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = InMemoryRunner(app_name=app_config.app_name, app=adk_app)

    # Collect initial snapshots
    snapshot = await _collect_all_snapshots(registry)
    if "local" in snapshot:
        await db.save_snapshot(snapshot["local"])

    # Create initial session
    session_state = {
        "risk_evaluator": risk_evaluator,
        "risk_tolerance": rule_gate.threshold,
        "latest_snapshot": snapshot,
        "watch_mode": True,
        "house": app_config.house,
        "squire_name": app_config.squire_name,
        "squire_profile": app_config.squire_profile,
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
    )
    await db.create_session(session.id)

    # Signal handling for graceful shutdown
    shutdown = asyncio.Event()

    def _signal_handler(sig, frame):
        logger.info("Received %s, shutting down...", signal.Signals(sig).name)
        shutdown.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # Persist initial watch state
    started_at = datetime.now(UTC).isoformat()
    await _update_watch_state(
        db,
        {
            "status": "running",
            "started_at": started_at,
            "pid": str(os.getpid()),
            "cycle": "0",
            "last_cycle_at": "",
            "last_response": "",
            "session_id": session.id,
            "interval_minutes": str(watch_config.interval_minutes),
            "risk_tolerance": str(watch_tolerance),
        },
    )

    # Dispatch lifecycle notification
    await _dispatch(notifier, "watch.start", "Squire watch mode started.")
    logger.info(
        "Watch mode started — interval=%dm, threshold=%s, cycles_per_session=%d",
        watch_config.interval_minutes,
        watch_tolerance,
        watch_config.cycles_per_session,
    )

    cycle_count = 0
    last_cycle_error: str | None = None

    try:
        while not shutdown.is_set():
            cycle_count += 1
            cycle_start = datetime.now(UTC).isoformat()

            await db.set_watch_state("cycle", str(cycle_count))
            await db.set_watch_state("last_cycle_at", cycle_start)

            # Collect fresh snapshots
            try:
                snapshot = await _collect_all_snapshots(registry)
                if "local" in snapshot:
                    await db.save_snapshot(snapshot["local"])
                session.state["latest_snapshot"] = snapshot
            except Exception:
                logger.debug("Snapshot collection failed", exc_info=True)

            # Reset per-cycle state
            call_tracker.reset()

            # Build prompt with error context from previous cycle
            prompt = watch_config.checkin_prompt
            if last_cycle_error:
                prompt = (
                    f"Note: the previous watch cycle encountered an error: {last_cycle_error}\n"
                    "Adjust your approach if needed (e.g. skip unavailable tools).\n\n"
                    f"{prompt}"
                )

            # Run the watch cycle
            try:
                response_text = await asyncio.wait_for(
                    _run_cycle(runner, session, agent, prompt, app_config),
                    timeout=watch_config.cycle_timeout_seconds,
                )
                last_cycle_error = None
                if response_text:
                    await db.save_message(session_id=session.id, role="assistant", content=response_text)
                    await db.set_watch_state("last_response", response_text[:500])
                    logger.info("Cycle %d:\n%s", cycle_count, response_text)
            except TimeoutError:
                last_cycle_error = f"Cycle timed out after {watch_config.cycle_timeout_seconds}s"
                logger.warning("Cycle %d timed out after %ds", cycle_count, watch_config.cycle_timeout_seconds)
                await db.set_watch_state("last_response", f"[timeout after {watch_config.cycle_timeout_seconds}s]")
                await _dispatch(notifier, "watch.error", f"Watch cycle {cycle_count} timed out.")
            except Exception as e:
                last_cycle_error = f"{type(e).__name__}: {e}"
                logger.error("Cycle %d failed: %s", cycle_count, e, exc_info=True)
                await db.set_watch_state("last_response", f"[error: {e}]")
                await _dispatch(notifier, "watch.error", f"Watch cycle {cycle_count} failed.")

            # Session rotation
            if cycle_count >= watch_config.cycles_per_session:
                logger.info("Rotating session after %d cycles", cycle_count)
                try:
                    summary = await asyncio.wait_for(
                        _run_cycle(
                            runner,
                            session,
                            agent,
                            "Summarize your observations and actions from this session in a few sentences.",
                            app_config,
                        ),
                        timeout=60,
                    )
                except (TimeoutError, Exception):
                    summary = "(session summary unavailable)"

                session = await runner.session_service.create_session(
                    app_name=app_config.app_name,
                    user_id=app_config.user_id,
                    state=session_state,
                )
                await db.create_session(session.id)
                await db.set_watch_state("session_id", session.id)

                if summary:
                    event = Event(
                        author="user",
                        invocation_id=Event.new_id(),
                        content=types.Content(
                            role="user",
                            parts=[types.Part(text=f"Context from previous session: {summary}")],
                        ),
                    )
                    await runner.session_service.append_event(session, event)

                cycle_count = 0

            # Sleep until next cycle (interruptible by shutdown signal)
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=watch_config.interval_minutes * 60)
            except TimeoutError:
                pass  # Normal — timeout means it's time for the next cycle

    finally:
        await db.set_watch_state("status", "stopped")
        await db.set_watch_state("stopped_at", datetime.now(UTC).isoformat())
        await _dispatch(notifier, "watch.stop", "Squire watch mode stopped.")
        logger.info("Watch mode stopped.")
        await registry.close_all()
        await notifier.close()
        await db.close()


async def _run_cycle(
    runner: InMemoryRunner,
    session,
    agent,
    prompt: str,
    app_config: AppConfig,
) -> str:
    """Inject a prompt and collect the agent's response."""
    message = types.Content(parts=[types.Part(text=prompt)])
    response_parts = []

    async for event in runner.run_async(
        user_id=app_config.user_id,
        session_id=session.id,
        new_message=message,
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if getattr(part, "thought", False):
                continue
            if part.text and not part.function_call and not part.function_response:
                response_parts.append(part.text)

    return "".join(response_parts)


async def _update_watch_state(db: DatabaseService, state: dict[str, str]) -> None:
    """Persist multiple watch state key-value pairs."""
    for key, value in state.items():
        await db.set_watch_state(key, value)


async def _dispatch(notifier: WebhookDispatcher, category: str, summary: str) -> None:
    """Best-effort notification dispatch."""
    try:
        await notifier.dispatch(category=category, summary=summary)
    except Exception:
        logger.debug("Failed to dispatch %s notification", category, exc_info=True)


async def get_watch_status() -> dict[str, str] | None:
    """Read the current watch state from the database.

    Returns the watch state dict, or None if watch has never run.
    """
    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)
    try:
        state = await db.get_all_watch_state()
        return state if state else None
    finally:
        await db.close()


def run_watch() -> None:
    """Synchronous wrapper to start watch mode."""
    asyncio.run(start_watch())
