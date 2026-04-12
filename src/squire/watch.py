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
from uuid import uuid4

from agent_risk_engine import RuleGate
from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.genai import types

from .adk.runtime import AdkRuntime
from .adk.session_state import build_watch_session_state
from .agents.squire_agent import create_squire_agent
from .callbacks.risk_gate import create_risk_gate
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
from .skills import SkillService
from .system.registry import BackendRegistry
from .tokens import coalesce_token_count, extract_token_usage_from_event
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
from .watch_playbooks import route_playbooks_for_incidents

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

_WATCH_ROUTING_TIMEOUT_SECONDS = 15
_WATCH_ROUTING_MAX_LLM_CALLS = 4
_WATCH_ROUTING_LLM_TIMEOUT_SECONDS = 6.0


def _extract_token_usage_from_event(event) -> tuple[int | None, int | None, int | None]:
    """Extract provider-reported token counts from a watch-cycle event."""
    return extract_token_usage_from_event(event)


def _accumulate_token_count(current: int | None, event_value: int | None) -> int | None:
    """Track the latest non-null token usage in a cycle."""
    return coalesce_token_count(current, event_value)


def _short_uuid() -> str:
    return uuid4().hex[:12]


def _build_cycle_carryforward(outcome: dict) -> dict:
    """Compact tactical memory that can be injected into the next cycle."""
    return {
        "status": outcome.get("cycle_status", "unknown"),
        "incident_key": outcome.get("incident_fingerprint"),
        "actions": str(outcome.get("actions", ""))[:400],
        "verification": str(outcome.get("verification", ""))[:400],
        "watchouts": str(outcome.get("escalation", ""))[:300],
    }


async def _close_cancelled_cycle(
    db: DatabaseService,
    *,
    cycle_id: str,
    watch_session_id: str,
    cycle_started_at: datetime,
) -> dict:
    """Close a pre-execution cycle when watch is stopped mid-loop."""
    duration_seconds = max((datetime.now(UTC) - cycle_started_at).total_seconds(), 0.0)
    outcome = {
        "cycle_status": "cancelled",
        "verification": "Cycle cancelled before execution because watch was stopped.",
        "incident_count": 0,
        "resolved": False,
        "escalated": False,
    }
    await db.close_watch_cycle(
        cycle_id,
        status="cancelled",
        duration_seconds=duration_seconds,
        tool_count=0,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=0,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        incident_key=None,
        outcome=outcome,
        error_reason="watch_stopped",
        cycle_carryforward=_build_cycle_carryforward(outcome),
    )
    return {
        "cycle_id": cycle_id,
        "watch_session_id": watch_session_id,
        "status": "cancelled",
        "tool_count": 0,
        "blocked_count": 0,
        "incident_count": 0,
        "resolved": False,
        "escalated": False,
        "total_tokens": 0,
    }


def _build_session_outcome(cycles: list[dict]) -> dict:
    """Deterministic session rollup with strict core fields."""
    if not cycles:
        return {
            "status": "empty",
            "goal_summary": "No cycles completed in this session.",
            "key_decisions": "",
            "persistent_risks": "",
            "open_actions": "",
            "memories_to_carry_forward": "",
            "parse_status": "ok",
            "failure_reason": "",
        }
    errors = sum(1 for c in cycles if c.get("status") != "ok")
    escalated = sum(1 for c in cycles if c.get("escalated"))
    resolved = sum(1 for c in cycles if c.get("resolved"))
    status = "error" if errors else "ok"
    return {
        "status": status,
        "goal_summary": f"Completed {len(cycles)} cycles with {resolved} resolved and {escalated} escalated outcomes.",
        "key_decisions": "Prioritized incident verification and low-risk remediation actions.",
        "persistent_risks": f"{escalated} escalated incident(s) require follow-up." if escalated else "",
        "open_actions": f"Review {errors} error cycle(s)." if errors else "",
        "memories_to_carry_forward": "Keep pseudo-filesystem false-positive suppression in context for future cycles.",
        "parse_status": "ok",
        "failure_reason": "",
    }


def _build_session_report(*, watch_id: str, watch_session_id: str, cycles: list[dict], outcome: dict) -> dict:
    """Create operator-friendly session report sections."""
    actions = sum(int(c.get("tool_count", 0)) for c in cycles)
    blocked = sum(int(c.get("blocked_count", 0)) for c in cycles)
    total_tokens = sum(int(c.get("total_tokens", 0) or 0) for c in cycles)
    incidents = sum(int(c.get("incident_count", 0) or 0) for c in cycles)
    return {
        "executive_summary": outcome.get("goal_summary", ""),
        "incidents_seen": f"{incidents} incident(s) observed across {len(cycles)} cycle(s).",
        "actions_taken": f"{actions} remediation action(s) executed.",
        "blocked_or_denied_actions": f"{blocked} blocked/denied action(s).",
        "verification_results": f"Session status: {outcome.get('status', 'unknown')}.",
        "open_risks": outcome.get("persistent_risks", ""),
        "recommended_follow_ups": outcome.get("open_actions", "") or "Continue watch with current controls.",
        "cost_usage": {"total_tokens": total_tokens, "cycle_count": len(cycles)},
        "meta": {"watch_id": watch_id, "watch_session_id": watch_session_id},
    }


def _build_watch_report(*, watch_id: str, sessions: list[dict], cycles: list[dict]) -> dict:
    """Create watch-completion rollup for operators."""
    session_ids = {str(session_id) for session_id in [s.get("watch_session_id") for s in sessions] if session_id}
    session_ids.update(str(session_id) for session_id in [c.get("watch_session_id") for c in cycles] if session_id)
    session_count = len(session_ids) if session_ids else len(sessions)
    total_tokens = sum(int(c.get("total_tokens", 0) or 0) for c in cycles)
    errors = sum(1 for c in cycles if c.get("status") != "ok")
    escalated = sum(1 for c in cycles if c.get("escalated"))
    incidents = sum(int(c.get("incident_count", 0) or 0) for c in cycles)
    action_count = sum(int(c.get("tool_count", 0)) for c in cycles)
    return {
        "run_summary": f"Watch {watch_id} completed with {session_count} session(s) and {len(cycles)} cycle(s).",
        "session_rollup": f"{session_count} session(s); {errors} error cycle(s).",
        "major_actions": f"{action_count} actions executed.",
        "error_and_timeout_analysis": f"{errors} cycles ended in error state.",
        "learning_memory_rollup": "Session carry-forward summaries generated for downstream sessions.",
        "next_watch_recommendations": (
            "Review escalated findings and adjust suppression rules for known pseudo-filesystem artifacts."
            if escalated or incidents
            else "No urgent follow-up required."
        ),
        "cost_usage": {"total_tokens": total_tokens},
    }


def _validated_live_watch_updates(
    payload: dict,
    watch_config: WatchConfig,
) -> tuple[dict, int | None]:
    """Validate and normalize live watch config updates before applying them."""
    updates = {key: payload[key] for key in _WATCH_LIVE_KEYS if key in payload}
    if updates:
        candidate = watch_config.model_dump()
        candidate.update(updates)
        validated = WatchConfig.model_validate(candidate)
        updates = {key: getattr(validated, key) for key in updates}

    risk_tolerance: int | None = None
    if "risk_tolerance" in payload:
        risk_tolerance = int(payload["risk_tolerance"])
        if not 1 <= risk_tolerance <= 5:
            raise ValueError("risk_tolerance must be between 1 and 5")
    return updates, risk_tolerance


async def _poll_commands(
    db: DatabaseService,
    shutdown: asyncio.Event,
    watch_config: WatchConfig | None,
    *,
    session_ref: list | None = None,
    session_state_template: dict | None = None,
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
                updates, risk_tolerance = _validated_live_watch_updates(payload, watch_config)

                for key, value in updates.items():
                    setattr(watch_config, key, value)
                if "interval_minutes" in updates:
                    await db.set_watch_state("interval_minutes", str(updates["interval_minutes"]))

                if risk_tolerance is not None:
                    threshold = risk_tolerance
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
    skill_service = SkillService(skills_config.path)

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
    notifier = NotificationRouter(webhook=webhook_dispatcher, email=email_notifier, db=db)
    set_db(db)
    set_notifier(notifier)

    # Preserve prior watch runs. Starting a new watch should append a new run,
    # not delete historical run/session/cycle/report records.

    # Load managed hosts from DB into the registry
    host_store = HostStore(db, registry)
    await host_store.load()

    # Build the risk evaluation pipeline
    guardrails = GuardrailsConfig()
    watch_tolerance = guardrails.watch_tolerance or guardrails.risk_tolerance
    watch_allowed_tools = set(guardrails.tools_allow) | set(guardrails.watch_tools_allow)
    watch_denied_tools = set(guardrails.tools_deny) | set(guardrails.watch_tools_deny)

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
    adk_runtime = AdkRuntime(app_name=app_config.app_name, db_path=db_config.path)
    adk_app = App(name=app_config.app_name, root_agent=agent)
    runner = adk_runtime.create_runner(app=adk_app)

    # Collect initial snapshots
    snapshot = await _collect_all_snapshots(registry)
    if "local" in snapshot:
        await db.save_snapshot(snapshot["local"])

    # Create initial session
    session_state = build_watch_session_state(
        latest_snapshot=snapshot,
        available_hosts=registry.host_names,
        host_configs={name: cfg.model_dump() for name, cfg in registry.host_configs.items()},
        risk_tolerance=watch_tolerance,
        risk_allowed_tools=watch_allowed_tools,
        risk_denied_tools=watch_denied_tools,
    )

    session = await runner.session_service.create_session(
        app_name=app_config.app_name,
        user_id=app_config.user_id,
        state=session_state,
    )
    await db.create_session(session.id)
    session_ref = [session]
    watch_id = f"watch_{_short_uuid()}"
    watch_session_id = f"wss_{_short_uuid()}"
    await db.create_watch_run(watch_id)
    await db.create_watch_session(watch_session_id, watch_id=watch_id, adk_session_id=session.id)
    emitter.set_scope(watch_id=watch_id, watch_session_id=watch_session_id)

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
            "stopped_at": "",
            "pid": str(os.getpid()),
            "cycle": "0",
            "cycle_id": "",
            "last_cycle_at": "",
            "last_response": "",
            "session_id": session.id,
            "watch_id": watch_id,
            "watch_session_id": watch_session_id,
            "interval_minutes": str(watch_config.interval_minutes),
            "risk_tolerance": str(watch_tolerance),
            "total_actions": "0",
            "total_blocked": "0",
            "total_errors": "0",
            "total_resolved": "0",
            "total_escalated": "0",
            "total_input_tokens": "0",
            "total_output_tokens": "0",
            "total_tokens": "0",
            "playbook_deterministic_match": "0",
            "playbook_semantic_match": "0",
            "playbook_generic_fallback": "0",
            "last_outcome": "{}",
        },
    )

    # Dispatch lifecycle notification
    await _dispatch(
        notifier,
        "watch.start",
        "Squire watch mode started.",
        watch_id=watch_id,
        watch_session_id=watch_session_id,
    )
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
    )

    cycle_count = 0
    last_cycle_error: str | None = None
    action_cooldowns: dict[str, int] = defaultdict(int)
    session_cycle_records: list[dict] = []
    all_cycle_records: list[dict] = []
    active_cycle_id: str | None = None
    active_cycle_started_at: datetime | None = None

    try:
        while not shutdown.is_set():
            cycle_count += 1
            cycle_started_at = datetime.now(UTC)
            cycle_start = cycle_started_at.isoformat()
            cycle_id = f"cyc_{_short_uuid()}"
            active_cycle_id = cycle_id
            active_cycle_started_at = cycle_started_at
            await db.create_watch_cycle(
                cycle_id,
                watch_id=watch_id,
                watch_session_id=watch_session_id,
                cycle_number=cycle_count,
            )

            await db.set_watch_state("cycle", str(cycle_count))
            await db.set_watch_state("cycle_id", cycle_id)
            await db.set_watch_state("last_cycle_at", cycle_start)

            # Poll for commands (e.g. stop or config update) before running cycle
            await _poll_commands(
                db,
                shutdown,
                watch_config,
                session_ref=session_ref,
                session_state_template=session_state,
            )
            if shutdown.is_set():
                if active_cycle_id and active_cycle_started_at:
                    cancelled_cycle = await _close_cancelled_cycle(
                        db,
                        cycle_id=active_cycle_id,
                        watch_session_id=watch_session_id,
                        cycle_started_at=active_cycle_started_at,
                    )
                    session_cycle_records.append(cancelled_cycle)
                    all_cycle_records.append(cancelled_cycle)
                active_cycle_id = None
                active_cycle_started_at = None
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
                        cycle_id=cycle_id,
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

            watch_skills = []
            playbook_skills = []
            try:
                watch_skills = skill_service.list_skills(enabled_only=True, trigger="watch")
                playbook_skills = [sk for sk in watch_skills if sk.incident_keys]
            except Exception:
                logger.debug("Failed to load watch skills", exc_info=True)

            playbook_path_counts = {
                "deterministic_single": 0,
                "tie_break": 0,
                "semantic": 0,
                "generic": 0,
            }
            try:
                playbooks, playbook_selections = await asyncio.wait_for(
                    route_playbooks_for_incidents(
                        incidents,
                        playbook_skills,
                        llm_config=llm_config,
                        max_llm_calls=_WATCH_ROUTING_MAX_LLM_CALLS,
                        llm_timeout_seconds=_WATCH_ROUTING_LLM_TIMEOUT_SECONDS,
                    ),
                    timeout=_WATCH_ROUTING_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.debug("Playbook routing failed; using generic fallback", exc_info=True)
                playbooks = []
                playbook_selections = []

            if playbook_selections:
                for selection in playbook_selections:
                    playbook_path_counts[selection.path_taken] = playbook_path_counts.get(selection.path_taken, 0) + 1
                    sel_name = selection.selected_playbook or "default-watch-triage"
                    await emitter.emit_phase(
                        cycle_count,
                        "playbook",
                        f"{selection.incident.key} -> {sel_name}",
                        details=(
                            f"path={selection.path_taken}, candidates={selection.candidate_count}, "
                            f"confidence={selection.confidence:.2f}, reason={selection.reasoning}"
                        ),
                    )
            prompt = build_cycle_contract_prompt(prompt, incidents, playbooks, blocked_signatures)

            # Append watch-triggered skills
            try:
                non_playbook_skills = [sk for sk in watch_skills if not sk.incident_keys]
                if non_playbook_skills:
                    skill_sections = []
                    for sk in non_playbook_skills:
                        if not sk.instructions:
                            continue
                        host_label = ",".join(sk.hosts)
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
            await emitter.emit_cycle_start(cycle_count, session.id, cycle_id=cycle_id)
            cycle_tool_count = 0
            cycle_input_tokens: int | None = None
            cycle_output_tokens: int | None = None
            cycle_total_tokens: int | None = None
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
                    cycle_input_tokens,
                    cycle_output_tokens,
                    cycle_total_tokens,
                ) = await asyncio.wait_for(
                    _run_cycle(
                        runner,
                        session,
                        agent,
                        prompt,
                        app_config,
                        emitter=emitter,
                        cycle=cycle_count,
                        cycle_id=cycle_id,
                        max_tool_calls=watch_config.max_tool_calls_per_cycle,
                        max_identical_actions=watch_config.max_identical_actions_per_cycle,
                        max_remote_actions=watch_config.max_remote_actions_per_cycle,
                    ),
                    timeout=watch_config.cycle_timeout_seconds,
                )
                last_cycle_error = None
                if response_text:
                    await db.save_message(
                        session_id=session.id,
                        role="assistant",
                        content=response_text,
                        input_tokens=cycle_input_tokens,
                        output_tokens=cycle_output_tokens,
                        total_tokens=cycle_total_tokens,
                    )
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
                outcome["playbook_selection"] = playbook_path_counts
                outcome["remote_tool_count"] = remote_tool_count
                outcome["input_tokens"] = cycle_input_tokens
                outcome["output_tokens"] = cycle_output_tokens
                outcome["total_tokens"] = cycle_total_tokens
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
                await _dispatch(
                    notifier,
                    "watch.error",
                    f"Watch cycle {cycle_count} timed out.",
                    watch_id=watch_id,
                    watch_session_id=watch_session_id,
                    cycle_id=cycle_id,
                )
                blocked_count = 0
                cycle_tool_count = 0
                cycle_input_tokens = None
                cycle_output_tokens = None
                cycle_total_tokens = None
                outcome = build_cycle_outcome(
                    incidents,
                    {},
                    tool_count=0,
                    blocked_count=0,
                    cycle_status="error",
                )
                outcome["playbook_selection"] = playbook_path_counts
                outcome["input_tokens"] = cycle_input_tokens
                outcome["output_tokens"] = cycle_output_tokens
                outcome["total_tokens"] = cycle_total_tokens
            except Exception as e:
                last_cycle_error = f"{type(e).__name__}: {e}"
                logger.error("Cycle %d failed: %s", cycle_count, e, exc_info=True)
                await db.set_watch_state("last_response", f"[error: {e}]")
                await _dispatch(
                    notifier,
                    "watch.error",
                    f"Watch cycle {cycle_count} failed.",
                    watch_id=watch_id,
                    watch_session_id=watch_session_id,
                    cycle_id=cycle_id,
                )
                blocked_count = 0
                cycle_tool_count = 0
                cycle_input_tokens = None
                cycle_output_tokens = None
                cycle_total_tokens = None
                outcome = build_cycle_outcome(
                    incidents,
                    {},
                    tool_count=0,
                    blocked_count=0,
                    cycle_status="error",
                )
                outcome["playbook_selection"] = playbook_path_counts
                outcome["input_tokens"] = cycle_input_tokens
                outcome["output_tokens"] = cycle_output_tokens
                outcome["total_tokens"] = cycle_total_tokens

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
                input_tokens=cycle_input_tokens,
                output_tokens=cycle_output_tokens,
                total_tokens=cycle_total_tokens,
                cycle_id=cycle_id,
            )
            error_reason = None if cycle_status == "ok" else (last_cycle_error or "cycle_error")
            cycle_carryforward = _build_cycle_carryforward(outcome)
            await db.close_watch_cycle(
                cycle_id,
                status=cycle_status,
                duration_seconds=cycle_duration,
                tool_count=cycle_tool_count,
                blocked_count=blocked_count,
                remote_tool_count=int(outcome.get("remote_tool_count", 0)),
                incident_count=int(outcome.get("incident_count", 0)),
                input_tokens=cycle_input_tokens,
                output_tokens=cycle_output_tokens,
                total_tokens=cycle_total_tokens,
                incident_key=outcome.get("incident_fingerprint"),
                outcome=outcome,
                error_reason=error_reason,
                cycle_carryforward=cycle_carryforward,
            )
            active_cycle_id = None
            active_cycle_started_at = None
            cycle_row = {
                "cycle_id": cycle_id,
                "watch_session_id": watch_session_id,
                "status": cycle_status,
                "tool_count": cycle_tool_count,
                "blocked_count": blocked_count,
                "incident_count": int(outcome.get("incident_count", 0)),
                "resolved": bool(outcome.get("resolved", False)),
                "escalated": bool(outcome.get("escalated", False)),
                "total_tokens": cycle_total_tokens or 0,
            }
            session_cycle_records.append(cycle_row)
            all_cycle_records.append(cycle_row)
            await _persist_watch_metrics(db, outcome)
            await _dispatch_outcome_notifications(
                db,
                notifier,
                cycle_count,
                outcome,
                watch_id=watch_id,
                watch_session_id=watch_session_id,
                cycle_id=cycle_id,
            )

            if watch_config.notify_on_action and cycle_tool_count > 0 and last_cycle_error is None:
                await _dispatch(
                    notifier,
                    "watch.action",
                    f"Watch cycle {cycle_count} executed {cycle_tool_count} tool call(s).",
                    watch_id=watch_id,
                    watch_session_id=watch_session_id,
                    cycle_id=cycle_id,
                )

            rotate_for_context = _session_event_count(session) > watch_config.max_context_events
            if rotate_for_context:
                logger.info(
                    "Rotating session early: event count exceeded max_context_events (%d)",
                    watch_config.max_context_events,
                )

            # Session rotation
            if cycle_count >= watch_config.cycles_per_session or rotate_for_context:
                old_session_id = session.id
                old_watch_session_id = watch_session_id
                logger.info("Rotating session after %d cycles", cycle_count)

                carryover = response_text[:500] if response_text else "(no prior context)"
                session_outcome = _build_session_outcome(session_cycle_records)
                session_report = _build_session_report(
                    watch_id=watch_id,
                    watch_session_id=old_watch_session_id,
                    cycles=session_cycle_records,
                    outcome=session_outcome,
                )
                session_report_id = f"wsr_{_short_uuid()}"
                session_report_pk = await db.create_watch_report(
                    session_report_id,
                    watch_id=watch_id,
                    watch_session_id=old_watch_session_id,
                    report_type="session",
                    status=session_outcome["status"],
                    title=f"Session report {old_watch_session_id}",
                    digest=session_report["executive_summary"],
                    report=session_report,
                )
                await db.close_watch_session(
                    old_watch_session_id,
                    status=session_outcome["status"],
                    cycle_count=len(session_cycle_records),
                    session_carryforward=session_outcome,
                    session_outcome=session_outcome,
                    session_report_id=session_report_pk,
                )

                session = await runner.session_service.create_session(
                    app_name=app_config.app_name,
                    user_id=app_config.user_id,
                    state=session_state,
                )
                await db.create_session(session.id)
                watch_session_id = f"wss_{_short_uuid()}"
                await db.create_watch_session(watch_session_id, watch_id=watch_id, adk_session_id=session.id)
                emitter.set_scope(watch_id=watch_id, watch_session_id=watch_session_id)
                await db.set_watch_state("session_id", session.id)
                await db.set_watch_state("watch_session_id", watch_session_id)

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
                session_cycle_records = []

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
            )

    finally:
        session_outcome = _build_session_outcome(session_cycle_records)
        session_report = _build_session_report(
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycles=session_cycle_records,
            outcome=session_outcome,
        )
        session_status = str(session_outcome.get("status", "error"))
        session_report_pk: int | None = None
        try:
            session_report_id = f"wsr_{_short_uuid()}"
            session_report_pk = await db.create_watch_report(
                session_report_id,
                watch_id=watch_id,
                watch_session_id=watch_session_id,
                report_type="session",
                status=session_status,
                title=f"Session report {watch_session_id}",
                digest=session_report["executive_summary"],
                report=session_report,
            )
        except Exception:
            logger.exception("Failed to persist final session report for %s", watch_session_id)
            session_status = "error"
            session_outcome = {
                **session_outcome,
                "status": "error",
                "failure_reason": "session_report_persist_failed",
            }
        try:
            await db.close_watch_session(
                watch_session_id,
                status="stopped" if session_status == "empty" else session_status,
                cycle_count=len(session_cycle_records),
                session_carryforward=session_outcome,
                session_outcome=session_outcome,
                session_report_id=session_report_pk,
            )
        except Exception:
            logger.exception("Failed to close watch session %s during shutdown", watch_session_id)
            session_status = "error"

        try:
            sessions_for_report = await db.list_watch_sessions_for_run(watch_id, page=1, per_page=1000)
        except Exception:
            logger.exception("Failed to list watch sessions for %s while building watch report", watch_id)
            sessions_for_report = [{"watch_session_id": watch_session_id, "status": session_status}]

        watch_report = _build_watch_report(
            watch_id=watch_id,
            sessions=sessions_for_report,
            cycles=all_cycle_records,
        )
        watch_report_id = f"wrp_{_short_uuid()}"
        watch_report_pk: int | None = None
        try:
            watch_status = "error" if any(c.get("status") == "error" for c in all_cycle_records) else "ok"
            if session_status == "error":
                watch_status = "error"
            watch_report_pk = await db.create_watch_report(
                watch_report_id,
                watch_id=watch_id,
                report_type="watch",
                status=watch_status,
                title=f"Watch completion report {watch_id}",
                digest=watch_report["run_summary"],
                report=watch_report,
            )
        except Exception:
            logger.exception("Failed to persist watch completion report for %s", watch_id)

        try:
            await db.close_watch_run(
                watch_id,
                status="stopped",
                watch_completion_report_id=watch_report_pk,
            )
        except Exception:
            logger.exception("Failed to close watch run %s during shutdown", watch_id)

        stopped_at = datetime.now(UTC).isoformat()
        try:
            await db.set_watch_state("status", "stopped")
            await db.set_watch_state("stopped_at", stopped_at)
        except Exception:
            logger.exception("Failed to update watch state during shutdown")

        try:
            await _dispatch(notifier, "watch.stop", "Squire watch mode stopped.", watch_id=watch_id)
        except Exception:
            logger.exception("Failed to dispatch watch.stop notification")
        logger.info("Watch mode stopped.")

        try:
            await registry.close_all()
        except Exception:
            logger.exception("Failed to close backend registry during watch shutdown")
        try:
            await notifier.close()
        except Exception:
            logger.exception("Failed to close notifier during watch shutdown")
        await db.close()


async def _run_cycle(
    runner: Runner,
    session,
    agent,
    prompt: str,
    app_config: AppConfig,
    emitter: WatchEventEmitter | None = None,
    cycle: int = 0,
    cycle_id: str | None = None,
    max_tool_calls: int = 0,
    max_identical_actions: int = 0,
    max_remote_actions: int = 0,
) -> tuple[str, int, int, list[str], int, int | None, int | None, int | None]:
    """Inject a prompt and collect the agent's response.

    Returns:
        A tuple of (
            response_text,
            tool_call_count,
            blocked_count,
            cooldown_signatures,
            remote_tool_count,
            input_tokens,
            output_tokens,
            total_tokens,
        ).
    """
    message = types.Content(parts=[types.Part(text=prompt)])
    response_parts: list[str] = []
    tool_count = 0
    blocked_count = 0
    remote_tool_count = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    signature_counts: dict[str, int] = defaultdict(int)
    cooldown_signatures: list[str] = []

    async for event in runner.run_async(
        user_id=app_config.user_id,
        session_id=session.id,
        new_message=message,
    ):
        event_input_tokens, event_output_tokens, event_total_tokens = _extract_token_usage_from_event(event)
        input_tokens = _accumulate_token_count(input_tokens, event_input_tokens)
        output_tokens = _accumulate_token_count(output_tokens, event_output_tokens)
        total_tokens = _accumulate_token_count(total_tokens, event_total_tokens)

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
                    await emitter.emit_tool_call(cycle, part.function_call.name, call_args, cycle_id=cycle_id)
                if max_identical_actions and signature_counts[signature] > max_identical_actions:
                    blocked_count += 1
                    response_parts.append(
                        f"\n[Cycle stopped: repeated action signature exceeded limit ({max_identical_actions})]"
                    )
                    return (
                        "".join(response_parts),
                        tool_count,
                        blocked_count,
                        cooldown_signatures,
                        remote_tool_count,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                    )
                if max_remote_actions and remote_tool_count > max_remote_actions:
                    blocked_count += 1
                    response_parts.append(f"\n[Cycle stopped: reached {max_remote_actions} remote action limit]")
                    return (
                        "".join(response_parts),
                        tool_count,
                        blocked_count,
                        cooldown_signatures,
                        remote_tool_count,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                    )
                if max_tool_calls and tool_count >= max_tool_calls:
                    logger.warning("Cycle %d hit tool call limit (%d)", cycle, max_tool_calls)
                    response_parts.append(f"\n[Cycle stopped: reached {max_tool_calls} tool call limit]")
                    return (
                        "".join(response_parts),
                        tool_count,
                        blocked_count,
                        cooldown_signatures,
                        remote_tool_count,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                    )
            elif part.function_response and emitter:
                output = str(part.function_response.response) if part.function_response.response else ""
                if "[BLOCKED]" in output or "[DENIED]" in output:
                    blocked_count += 1
                await emitter.emit_tool_result(cycle, part.function_response.name or "", output, cycle_id=cycle_id)
            elif part.text and not part.function_call and not part.function_response:
                response_parts.append(part.text)
                if emitter:
                    await emitter.emit_token(cycle, part.text, cycle_id=cycle_id)

    return (
        "".join(response_parts),
        tool_count,
        blocked_count,
        cooldown_signatures,
        remote_tool_count,
        input_tokens,
        output_tokens,
        total_tokens,
    )


def _session_event_count(session) -> int:
    """Best-effort count of session events using public session attributes."""
    events = getattr(session, "events", None)
    if isinstance(events, list):
        return len(events)
    return 0


async def _update_watch_state(db: DatabaseService, state: dict[str, str]) -> None:
    """Persist multiple watch state key-value pairs."""
    for key, value in state.items():
        await db.set_watch_state(key, value)


async def _dispatch(
    notifier: NotificationRouter,
    category: str,
    summary: str,
    *,
    watch_id: str | None = None,
    watch_session_id: str | None = None,
    cycle_id: str | None = None,
) -> None:
    """Best-effort notification dispatch."""
    try:
        await notifier.dispatch(
            category=category,
            summary=summary,
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )
    except Exception:
        logger.debug("Failed to dispatch %s notification", category, exc_info=True)


async def _persist_watch_metrics(db: DatabaseService, outcome: dict) -> None:
    total_actions = int(await db.get_watch_state("total_actions") or "0")
    total_blocked = int(await db.get_watch_state("total_blocked") or "0")
    total_errors = int(await db.get_watch_state("total_errors") or "0")
    total_resolved = int(await db.get_watch_state("total_resolved") or "0")
    total_escalated = int(await db.get_watch_state("total_escalated") or "0")
    total_input_tokens = int(await db.get_watch_state("total_input_tokens") or "0")
    total_output_tokens = int(await db.get_watch_state("total_output_tokens") or "0")
    total_tokens = int(await db.get_watch_state("total_tokens") or "0")
    total_playbook_deterministic = int(await db.get_watch_state("playbook_deterministic_match") or "0")
    total_playbook_semantic = int(await db.get_watch_state("playbook_semantic_match") or "0")
    total_playbook_generic = int(await db.get_watch_state("playbook_generic_fallback") or "0")
    playbook_selection = outcome.get("playbook_selection", {}) or {}
    totals = {
        "total_actions": total_actions + int(outcome.get("tool_count", 0)),
        "total_blocked": total_blocked + int(outcome.get("blocked_count", 0)),
        "total_errors": total_errors + (1 if outcome.get("cycle_status") != "ok" else 0),
        "total_resolved": total_resolved + (1 if outcome.get("resolved") else 0),
        "total_escalated": total_escalated + (1 if outcome.get("escalated") else 0),
        "total_input_tokens": total_input_tokens + int(outcome.get("input_tokens") or 0),
        "total_output_tokens": total_output_tokens + int(outcome.get("output_tokens") or 0),
        "total_tokens": total_tokens + int(outcome.get("total_tokens") or 0),
        "playbook_deterministic_match": total_playbook_deterministic
        + int(playbook_selection.get("deterministic_single", 0))
        + int(playbook_selection.get("tie_break", 0)),
        "playbook_semantic_match": total_playbook_semantic + int(playbook_selection.get("semantic", 0)),
        "playbook_generic_fallback": total_playbook_generic + int(playbook_selection.get("generic", 0)),
    }
    for key, value in totals.items():
        await db.set_watch_state(key, str(value))
    await db.set_watch_state("last_outcome", json.dumps(outcome))


async def _dispatch_outcome_notifications(
    db: DatabaseService,
    notifier: NotificationRouter,
    cycle: int,
    outcome: dict,
    *,
    watch_id: str | None = None,
    watch_session_id: str | None = None,
    cycle_id: str | None = None,
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
                watch_id=watch_id,
                watch_session_id=watch_session_id,
                cycle_id=cycle_id,
            )
            await db.set_watch_state("last_notified_incident", incident_fingerprint)
    if int(outcome.get("tool_count", 0)) > 0:
        await _dispatch(
            notifier,
            "watch.remediation",
            f"Cycle {cycle}: executed {outcome.get('tool_count', 0)} remediation action(s).",
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )
    if outcome.get("resolved"):
        await _dispatch(
            notifier,
            "watch.verification",
            f"Cycle {cycle}: remediation verified as resolved.",
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )
    if outcome.get("escalated"):
        await _dispatch(
            notifier,
            "watch.escalation",
            f"Cycle {cycle}: escalation required for unresolved issue.",
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )
    if cycle % 6 == 0:
        summary = (
            f"Cycle {cycle} digest: actions={await db.get_watch_state('total_actions') or '0'}, "
            f"blocked={await db.get_watch_state('total_blocked') or '0'}, "
            f"resolved={await db.get_watch_state('total_resolved') or '0'}, "
            f"escalated={await db.get_watch_state('total_escalated') or '0'}."
        )
        await _dispatch(
            notifier,
            "watch.digest",
            summary,
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )


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
