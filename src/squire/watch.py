"""Autonomous watch mode — headless monitoring loop.

Runs Squire headlessly, periodically injecting a check-in prompt and
letting the agent reason about system state. Tools above the risk threshold
are denied outright; notifications are dispatched for actions and blocks.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from collections import defaultdict
from datetime import UTC, datetime

from agent_risk_engine import RiskEvaluator, RuleGate
from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agents.squire_agent import create_squire_agent
from .callbacks.risk_gate import build_pattern_analyzer, create_risk_gate
from .config import (
    AppConfig,
    DatabaseConfig,
    GuardrailsConfig,
    LLMConfig,
    NotificationsConfig,
    SkillsConfig,
    WatchConfig,
)
from .database.service import DatabaseService
from .hosts.store import HostStore
from .main import _collect_all_snapshots
from .notifications.alert_evaluator import evaluate_alerts
from .notifications.email import EmailNotifier
from .notifications.router import NotificationRouter
from .notifications.webhook import WebhookDispatcher
from .system.registry import BackendRegistry
from .tools import TOOL_RISK_LEVELS, set_db, set_notifier, set_registry
from .watch_autonomy import (
    action_signature,
    build_cycle_contract_prompt,
    build_cycle_outcome,
    detect_incidents,
    dominant_incident_key,
    parse_contract_sections,
)
from .watch_emitter import WatchEventEmitter
from .watch_playbooks import select_playbooks

load_dotenv()

logger = logging.getLogger(__name__)

# Keys allowed on WatchConfig from a live ``update_config`` command (JSON payload).
_WATCH_LIVE_KEYS = frozenset(
    {
        "interval_minutes",
        "max_tool_calls_per_cycle",
        "cycle_timeout_seconds",
        "checkin_prompt",
        "notify_on_action",
        "notify_on_blocked",
        "cycles_per_session",
        "max_context_events",
        "max_identical_actions_per_cycle",
        "blocked_action_cooldown_cycles",
        "max_remote_actions_per_cycle",
    }
)


async def _poll_commands(
    db: DatabaseService,
    shutdown: asyncio.Event,
    watch_config: WatchConfig | None,
    *,
    session_ref: list | None = None,
    session_state_template: dict | None = None,
    risk_evaluator: RiskEvaluator | None = None,
) -> None:
    """Process any pending watch commands from the database."""
    commands = await db.get_pending_watch_commands()
    for cmd in commands:
        cmd_id = cmd["id"]
        command = cmd["command"]
        try:
            if command == "stop":
                shutdown.set()
                await db.update_watch_command_status(cmd_id, "completed")
            elif command == "update_config" and watch_config is not None:
                payload = json.loads(cmd["payload"] or "{}")
                for key in _WATCH_LIVE_KEYS:
                    if key in payload:
                        setattr(watch_config, key, payload[key])
                if "interval_minutes" in payload:
                    await db.set_watch_state("interval_minutes", str(payload["interval_minutes"]))
                if "risk_tolerance" in payload and risk_evaluator is not None:
                    threshold = int(payload["risk_tolerance"])
                    risk_evaluator.rule_gate.threshold = threshold
                    if session_state_template is not None:
                        session_state_template["risk_tolerance"] = threshold
                    sess = session_ref[0] if session_ref and session_ref[0] is not None else None
                    if sess is not None:
                        sess.state["risk_tolerance"] = threshold
                    await db.set_watch_state("risk_tolerance", str(threshold))
                await db.update_watch_command_status(cmd_id, "completed")
                logger.info("Applied config update: %s", payload)
            elif command == "start":
                await db.update_watch_command_status(cmd_id, "completed")
            else:
                await db.update_watch_command_status(cmd_id, "failed", error=f"Unknown command: {command}")
        except Exception as e:
            await db.update_watch_command_status(cmd_id, "failed", error=str(e))


async def _interruptible_sleep(
    db: DatabaseService,
    shutdown: asyncio.Event,
    interval_seconds: float,
    poll_seconds: float = 5.0,
    watch_config: WatchConfig | None = None,
    *,
    session_ref: list | None = None,
    session_state_template: dict | None = None,
    risk_evaluator: RiskEvaluator | None = None,
) -> None:
    """Sleep in short increments, polling for commands between sleeps."""
    elapsed = 0.0
    while elapsed < interval_seconds and not shutdown.is_set():
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=min(poll_seconds, interval_seconds - elapsed))
        except TimeoutError:
            pass
        elapsed += poll_seconds
        if not shutdown.is_set():
            await _poll_commands(
                db,
                shutdown,
                watch_config,
                session_ref=session_ref,
                session_state_template=session_state_template,
                risk_evaluator=risk_evaluator,
            )


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
    skills_config = SkillsConfig()

    # Create backend registry (hosts loaded from DB below)
    registry = BackendRegistry()
    set_registry(registry)

    # Initialize database and webhook dispatcher
    db = DatabaseService(db_config.path)
    emitter = WatchEventEmitter(db)
    webhook_dispatcher = WebhookDispatcher(notif_config)
    email_notifier = None
    if notif_config.email and notif_config.email.enabled:
        email_notifier = EmailNotifier(notif_config.email)
    notifier = NotificationRouter(webhook=webhook_dispatcher, email=email_notifier)
    set_db(db)
    set_notifier(notifier)

    # Load managed hosts from DB into the registry
    host_store = HostStore(db, registry)
    await host_store.load()

    # Build the risk evaluation pipeline
    guardrails = GuardrailsConfig()
    watch_tolerance = guardrails.watch_tolerance or guardrails.risk_tolerance
    rule_gate = RuleGate(
        threshold=watch_tolerance,
        strict=True,  # Always strict in watch mode — deny, don't prompt
        allowed=set(guardrails.tools_allow) | set(guardrails.watch_tools_allow),
        # approve intentionally omitted — watch mode has no approval provider
        denied=set(guardrails.tools_deny) | set(guardrails.watch_tools_deny),
    )
    risk_evaluator = RiskEvaluator(rule_gate=rule_gate, analyzer=build_pattern_analyzer())

    # Build the agent with headless risk gate
    block_notifier = notifier if watch_config.notify_on_blocked else None

    def _make_headless_risk_gate(tool_risk_levels: dict[str, int], agent_threshold: int | None = None):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            risk_overrides=dict(guardrails.tools_risk_overrides),
            default_threshold=agent_threshold,
            headless=True,
            notifier=block_notifier,
        )

    if app_config.multi_agent:
        agent_tolerances = {
            "Monitor": guardrails.monitor_tolerance,
            "Container": guardrails.container_tolerance,
            "Admin": guardrails.admin_tolerance,
            "Notifier": guardrails.notifier_tolerance,
        }

        def _per_agent_builder(agent_name: str):
            tol = agent_tolerances.get(agent_name)
            threshold = RuleGate(threshold=tol).threshold if tol else None

            def factory(tool_risk_levels: dict[str, int]):
                return _make_headless_risk_gate(tool_risk_levels, agent_threshold=threshold)

            return factory

        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory_builder=_per_agent_builder,
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
        "available_hosts": registry.host_names,
        "host_configs": {name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
    }

    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
    )
    await db.create_session(session.id)
    session_ref = [session]

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
            "total_actions": "0",
            "total_blocked": "0",
            "total_errors": "0",
            "total_resolved": "0",
            "total_escalated": "0",
            "last_outcome": "{}",
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

    # Cleanup stale data and process any pending start commands
    await db.cleanup_watch_data()
    await _poll_commands(
        db,
        shutdown,
        watch_config,
        session_ref=session_ref,
        session_state_template=session_state,
        risk_evaluator=risk_evaluator,
    )

    cycle_count = 0
    last_cycle_error: str | None = None
    action_cooldowns: dict[str, int] = defaultdict(int)

    try:
        while not shutdown.is_set():
            cycle_count += 1
            cycle_start = datetime.now(UTC).isoformat()

            await db.set_watch_state("cycle", str(cycle_count))
            await db.set_watch_state("last_cycle_at", cycle_start)

            # Poll for commands (e.g. stop or config update) before running cycle
            await _poll_commands(
                db,
                shutdown,
                watch_config,
                session_ref=session_ref,
                session_state_template=session_state,
                risk_evaluator=risk_evaluator,
            )
            if shutdown.is_set():
                break

            # Collect fresh snapshots
            incidents = []
            try:
                snapshot = await _collect_all_snapshots(registry)
                if "local" in snapshot:
                    await db.save_snapshot(snapshot["local"])
                session.state["latest_snapshot"] = snapshot
                incidents = detect_incidents(snapshot)
                for incident in incidents:
                    await emitter.emit_incident(
                        cycle_count,
                        key=incident.key,
                        severity=incident.severity,
                        title=incident.title,
                        detail=incident.detail,
                        host=incident.host,
                    )

                # Evaluate alert rules against fresh snapshot
                try:
                    fired = await evaluate_alerts(db, notifier, snapshot)
                    if fired > 0 and emitter:
                        await emitter.emit_tool_result(cycle_count, "alert_evaluator", f"{fired} alert(s) fired")
                except Exception:
                    logger.debug("Alert evaluation failed", exc_info=True)
            except Exception:
                logger.debug("Snapshot collection failed", exc_info=True)

            # Build prompt with error context from previous cycle
            prompt = watch_config.checkin_prompt
            if last_cycle_error:
                prompt = (
                    f"Note: the previous watch cycle encountered an error: {last_cycle_error}\n"
                    "Adjust your approach if needed (e.g. skip unavailable tools).\n\n"
                    f"{prompt}"
                )

            # Decay action cooldowns and expose active blocks to the risk gate.
            blocked_signatures = []
            for signature in list(action_cooldowns):
                action_cooldowns[signature] -= 1
                if action_cooldowns[signature] <= 0:
                    del action_cooldowns[signature]
                else:
                    blocked_signatures.append(signature)
            session.state["watch_blocked_action_signatures"] = blocked_signatures
            session.state["watch_max_identical_actions_per_cycle"] = watch_config.max_identical_actions_per_cycle
            session.state["watch_max_remote_actions_per_cycle"] = watch_config.max_remote_actions_per_cycle

            playbooks = select_playbooks(incidents)
            prompt = build_cycle_contract_prompt(prompt, incidents, playbooks, blocked_signatures)

            # Append watch-triggered skills
            try:
                from .skills import SkillService

                skill_service = SkillService(skills_config.path)
                watch_skills = skill_service.list_skills(enabled_only=True, trigger="watch")
                if watch_skills:
                    skill_sections = []
                    for sk in watch_skills:
                        if not sk.instructions:
                            continue
                        host_label = sk.host
                        skill_sections.append(f"### Skill: {sk.name} (host: {host_label})\n{sk.instructions}")
                    if skill_sections:
                        prompt += (
                            "\n\nIn addition to your routine check-in, execute the following skills:\n\n"
                            + "\n\n".join(skill_sections)
                        )
            except Exception:
                logger.debug("Failed to load watch skills", exc_info=True)

            # Run the watch cycle
            cycle_start_time = datetime.now(UTC)
            await emitter.emit_cycle_start(cycle_count, session.id)
            cycle_tool_count = 0
            response_text = ""
            try:
                await emitter.emit_phase(
                    cycle_count,
                    "detect",
                    f"Detected {len(incidents)} incident(s)",
                    details="; ".join(f"{i.title}@{i.host}" for i in incidents[:8]),
                )
                (
                    response_text,
                    cycle_tool_count,
                    blocked_count,
                    cycle_signatures,
                    remote_tool_count,
                ) = await asyncio.wait_for(
                    _run_cycle(
                        runner,
                        session,
                        agent,
                        prompt,
                        app_config,
                        emitter=emitter,
                        cycle=cycle_count,
                        max_tool_calls=watch_config.max_tool_calls_per_cycle,
                        max_identical_actions=watch_config.max_identical_actions_per_cycle,
                        max_remote_actions=watch_config.max_remote_actions_per_cycle,
                    ),
                    timeout=watch_config.cycle_timeout_seconds,
                )
                last_cycle_error = None
                if response_text:
                    await db.save_message(session_id=session.id, role="assistant", content=response_text)
                    await db.set_watch_state("last_response", response_text[:500])
                    logger.info("Cycle %d:\n%s", cycle_count, response_text)

                response_sections = parse_contract_sections(response_text)
                if response_sections.get("rca hypotheses"):
                    await emitter.emit_phase(
                        cycle_count,
                        "rca",
                        "RCA hypotheses generated",
                        details=response_sections["rca hypotheses"][:600],
                    )
                if response_sections.get("action plan and actions taken"):
                    await emitter.emit_phase(
                        cycle_count,
                        "remediate",
                        "Remediation actions planned/executed",
                        details=response_sections["action plan and actions taken"][:600],
                    )
                outcome = build_cycle_outcome(
                    incidents,
                    response_sections,
                    tool_count=cycle_tool_count,
                    blocked_count=blocked_count,
                    cycle_status="ok",
                )
                outcome["remote_tool_count"] = remote_tool_count
                issue_key = dominant_incident_key(incidents)
                if issue_key:
                    outcome["incident_fingerprint"] = issue_key
                await emitter.emit_phase(
                    cycle_count,
                    "verify",
                    "Verification completed",
                    details=outcome["verification"],
                )
                if outcome.get("escalated"):
                    await emitter.emit_phase(
                        cycle_count,
                        "escalate",
                        "Escalation required",
                        details=outcome.get("escalation", ""),
                    )

                for signature in cycle_signatures:
                    action_cooldowns[signature] = max(
                        action_cooldowns.get(signature, 0),
                        watch_config.blocked_action_cooldown_cycles,
                    )
            except TimeoutError:
                last_cycle_error = f"Cycle timed out after {watch_config.cycle_timeout_seconds}s"
                logger.warning("Cycle %d timed out after %ds", cycle_count, watch_config.cycle_timeout_seconds)
                await db.set_watch_state("last_response", f"[timeout after {watch_config.cycle_timeout_seconds}s]")
                await _dispatch(notifier, "watch.error", f"Watch cycle {cycle_count} timed out.")
                blocked_count = 0
                cycle_tool_count = 0
                outcome = build_cycle_outcome(
                    incidents,
                    {},
                    tool_count=0,
                    blocked_count=0,
                    cycle_status="error",
                )
            except Exception as e:
                last_cycle_error = f"{type(e).__name__}: {e}"
                logger.error("Cycle %d failed: %s", cycle_count, e, exc_info=True)
                await db.set_watch_state("last_response", f"[error: {e}]")
                await _dispatch(notifier, "watch.error", f"Watch cycle {cycle_count} failed.")
                blocked_count = 0
                cycle_tool_count = 0
                outcome = build_cycle_outcome(
                    incidents,
                    {},
                    tool_count=0,
                    blocked_count=0,
                    cycle_status="error",
                )

            cycle_duration = (datetime.now(UTC) - cycle_start_time).total_seconds()
            cycle_status = "ok" if last_cycle_error is None else "error"
            outcome["cycle_status"] = cycle_status
            await emitter.emit_cycle_end(
                cycle_count,
                cycle_status,
                cycle_duration,
                tool_count=cycle_tool_count,
                blocked_count=blocked_count,
                outcome=outcome,
            )
            await _persist_watch_metrics(db, outcome)
            await _dispatch_outcome_notifications(db, notifier, cycle_count, outcome)

            if watch_config.notify_on_action and cycle_tool_count > 0 and last_cycle_error is None:
                await _dispatch(
                    notifier,
                    "watch.action",
                    f"Watch cycle {cycle_count} executed {cycle_tool_count} tool call(s).",
                )

            # Prune session history to bound context size
            pruned = _prune_session_history(runner, session, watch_config.max_context_events)
            if pruned > 0:
                logger.debug("Pruned %d old events from session history", pruned)

            # Session rotation
            if cycle_count >= watch_config.cycles_per_session:
                old_session_id = session.id
                logger.info("Rotating session after %d cycles", cycle_count)

                carryover = response_text[:500] if response_text else "(no prior context)"

                session = await runner.session_service.create_session(
                    app_name=app_config.app_name,
                    user_id=app_config.user_id,
                    state=session_state,
                )
                await db.create_session(session.id)
                await db.set_watch_state("session_id", session.id)

                carryover_event = Event(
                    author="user",
                    invocation_id=Event.new_id(),
                    content=types.Content(
                        role="user",
                        parts=[types.Part(text=f"Context from previous session: {carryover}")],
                    ),
                )
                await runner.session_service.append_event(session, carryover_event)

                # Free old session from in-memory storage
                try:
                    await runner.session_service.delete_session(
                        app_name=app_config.app_name,
                        user_id=app_config.user_id,
                        session_id=old_session_id,
                    )
                except Exception:
                    logger.debug("Failed to delete old session %s", old_session_id, exc_info=True)

                await emitter.emit_session_rotated(cycle_count, old_session_id, session.id)
                cycle_count = 0
                session_ref[0] = session

            if cycle_count % 10 == 0:
                await db.cleanup_watch_data()

            # Sleep until next cycle (interruptible by shutdown signal or commands)
            await _interruptible_sleep(
                db,
                shutdown,
                watch_config.interval_minutes * 60,
                watch_config=watch_config,
                session_ref=session_ref,
                session_state_template=session_state,
                risk_evaluator=risk_evaluator,
            )

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
    emitter: WatchEventEmitter | None = None,
    cycle: int = 0,
    max_tool_calls: int = 0,
    max_identical_actions: int = 0,
    max_remote_actions: int = 0,
) -> tuple[str, int, int, list[str], int]:
    """Inject a prompt and collect the agent's response.

    Returns:
        A tuple of (response_text, tool_call_count, blocked_count, cooldown_signatures, remote_tool_count).
    """
    message = types.Content(parts=[types.Part(text=prompt)])
    response_parts: list[str] = []
    tool_count = 0
    blocked_count = 0
    remote_tool_count = 0
    signature_counts: dict[str, int] = defaultdict(int)
    cooldown_signatures: list[str] = []

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
            if part.function_call:
                tool_count += 1
                call_args = dict(part.function_call.args or {})
                signature = action_signature(part.function_call.name, call_args)
                signature_counts[signature] += 1
                if signature_counts[signature] > 1:
                    cooldown_signatures.append(signature)
                if call_args.get("host", "local") != "local":
                    remote_tool_count += 1
                if emitter:
                    await emitter.emit_tool_call(cycle, part.function_call.name, call_args)
                if max_identical_actions and signature_counts[signature] > max_identical_actions:
                    blocked_count += 1
                    response_parts.append(
                        f"\n[Cycle stopped: repeated action signature exceeded limit ({max_identical_actions})]"
                    )
                    return "".join(response_parts), tool_count, blocked_count, cooldown_signatures, remote_tool_count
                if max_remote_actions and remote_tool_count > max_remote_actions:
                    blocked_count += 1
                    response_parts.append(f"\n[Cycle stopped: reached {max_remote_actions} remote action limit]")
                    return "".join(response_parts), tool_count, blocked_count, cooldown_signatures, remote_tool_count
                if max_tool_calls and tool_count >= max_tool_calls:
                    logger.warning("Cycle %d hit tool call limit (%d)", cycle, max_tool_calls)
                    response_parts.append(f"\n[Cycle stopped: reached {max_tool_calls} tool call limit]")
                    return "".join(response_parts), tool_count, blocked_count, cooldown_signatures, remote_tool_count
            elif part.function_response and emitter:
                output = str(part.function_response.response) if part.function_response.response else ""
                if "[BLOCKED]" in output or "[DENIED]" in output:
                    blocked_count += 1
                await emitter.emit_tool_result(cycle, part.function_response.name or "", output)
            elif part.text and not part.function_call and not part.function_response:
                response_parts.append(part.text)
                if emitter:
                    await emitter.emit_token(cycle, part.text)

    return "".join(response_parts), tool_count, blocked_count, cooldown_signatures, remote_tool_count


def _prune_session_history(runner: InMemoryRunner, session, max_events: int) -> int:
    """Trim old events from the ADK session to bound context size.

    Directly accesses the InMemorySessionService storage to truncate
    the event list in-place, keeping only the most recent ``max_events``.

    Returns the number of events pruned.
    """
    try:
        storage = runner.session_service.sessions
        stored = storage.get(session.app_name, {}).get(session.user_id, {}).get(session.id)
        if stored is None or len(stored.events) <= max_events:
            return 0

        pruned = len(stored.events) - max_events
        stored.events = stored.events[-max_events:]
        session.events = session.events[-max_events:]
        return pruned
    except Exception:
        logger.debug("Failed to prune session history", exc_info=True)
        return 0


async def _update_watch_state(db: DatabaseService, state: dict[str, str]) -> None:
    """Persist multiple watch state key-value pairs."""
    for key, value in state.items():
        await db.set_watch_state(key, value)


async def _dispatch(notifier: NotificationRouter, category: str, summary: str) -> None:
    """Best-effort notification dispatch."""
    try:
        await notifier.dispatch(category=category, summary=summary)
    except Exception:
        logger.debug("Failed to dispatch %s notification", category, exc_info=True)


async def _persist_watch_metrics(db: DatabaseService, outcome: dict) -> None:
    total_actions = int(await db.get_watch_state("total_actions") or "0")
    total_blocked = int(await db.get_watch_state("total_blocked") or "0")
    total_errors = int(await db.get_watch_state("total_errors") or "0")
    total_resolved = int(await db.get_watch_state("total_resolved") or "0")
    total_escalated = int(await db.get_watch_state("total_escalated") or "0")
    totals = {
        "total_actions": total_actions + int(outcome.get("tool_count", 0)),
        "total_blocked": total_blocked + int(outcome.get("blocked_count", 0)),
        "total_errors": total_errors + (1 if outcome.get("cycle_status") != "ok" else 0),
        "total_resolved": total_resolved + (1 if outcome.get("resolved") else 0),
        "total_escalated": total_escalated + (1 if outcome.get("escalated") else 0),
    }
    for key, value in totals.items():
        await db.set_watch_state(key, str(value))
    await db.set_watch_state("last_outcome", json.dumps(outcome))


async def _dispatch_outcome_notifications(
    db: DatabaseService,
    notifier: NotificationRouter,
    cycle: int,
    outcome: dict,
) -> None:
    incident_count = int(outcome.get("incident_count", 0))
    if incident_count > 0:
        incident_fingerprint = str(outcome.get("incident_fingerprint", "n/a"))
        previous = await db.get_watch_state("last_notified_incident")
        if previous != incident_fingerprint:
            await _dispatch(
                notifier,
                "watch.incident_detected",
                f"Cycle {cycle}: detected {incident_count} incident(s) ({incident_fingerprint}).",
            )
            await db.set_watch_state("last_notified_incident", incident_fingerprint)
    if int(outcome.get("tool_count", 0)) > 0:
        await _dispatch(
            notifier,
            "watch.remediation",
            f"Cycle {cycle}: executed {outcome.get('tool_count', 0)} remediation action(s).",
        )
    if outcome.get("resolved"):
        await _dispatch(notifier, "watch.verification", f"Cycle {cycle}: remediation verified as resolved.")
    if outcome.get("escalated"):
        await _dispatch(notifier, "watch.escalation", f"Cycle {cycle}: escalation required for unresolved issue.")
    if cycle % 6 == 0:
        summary = (
            f"Cycle {cycle} digest: actions={await db.get_watch_state('total_actions') or '0'}, "
            f"blocked={await db.get_watch_state('total_blocked') or '0'}, "
            f"resolved={await db.get_watch_state('total_resolved') or '0'}, "
            f"escalated={await db.get_watch_state('total_escalated') or '0'}."
        )
        await _dispatch(notifier, "watch.digest", summary)


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
