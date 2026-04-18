"""In-process watch controller.

Replaces the subprocess-based watch model. The controller runs as an asyncio
task inside the FastAPI process (scheduled from the lifespan context) and
owns the full autonomous watch loop. Start/stop/reload are driven by in-memory
``asyncio.Event`` signals instead of DB-polled commands.

A DB-backed ``watch_holder`` lock (in ``watch_state``) protects against two
controllers running against the same database — e.g. an accidental second
uvicorn worker, or the standalone ``squire watch`` CLI invoked while the web
server is already running watch.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from agent_risk_engine import RuleGate
from google.adk.apps import App
from google.adk.events.event import Event
from google.genai import types

from .adk.runtime import AdkRuntime
from .adk.session_state import build_watch_session_state
from .agents.squire_agent import create_squire_agent
from .callbacks.risk_gate import create_risk_gate
from .config import (
    AppConfig,
    GuardrailsConfig,
    LLMConfig,
    NotificationsConfig,
    SkillsConfig,
    WatchConfig,
)
from .database.service import DatabaseService
from .hosts.store import HostStore
from .main import _collect_all_snapshots
from .notifications.email import EmailNotifier
from .notifications.router import NotificationRouter
from .notifications.webhook import WebhookDispatcher
from .skills import SkillService
from .system.registry import BackendRegistry
from .tools import TOOL_RISK_LEVELS, set_notifier
from .watch_autonomy import (
    build_cycle_contract_prompt,
    build_cycle_outcome,
    detect_incidents,
    dominant_incident_key,
    parse_contract_sections,
)
from .watch_emitter import WatchEventEmitter
from .watch_loop import (
    build_cycle_carryforward,
    build_session_outcome,
    build_session_report,
    build_watch_report,
    close_cancelled_cycle,
    dispatch,
    dispatch_outcome_notifications,
    persist_watch_metrics,
    run_cycle,
    session_event_count,
    short_uuid,
)
from .watch_playbooks import route_playbooks_for_incidents

logger = logging.getLogger(__name__)

ControllerState = Literal["stopped", "starting", "running", "failed"]

_HOLDER_TTL_SECONDS = 90
_HOLDER_HEARTBEAT_SECONDS = 30
_STOP_TIMEOUT_DEFAULT = 30.0
_ALL_CYCLES_MAX = 500  # cap for all_cycle_records so indefinite runs don't leak memory
_WATCH_ROUTING_TIMEOUT_SECONDS = 15
_WATCH_ROUTING_MAX_LLM_CALLS = 4
_WATCH_ROUTING_LLM_TIMEOUT_SECONDS = 6.0


@dataclass
class StartResult:
    """Result of calling ``WatchController.start``."""

    status: Literal["ok", "already_running", "holder_busy", "error"]
    message: str

    @classmethod
    def ok(cls) -> StartResult:
        return cls(status="ok", message="Watch starting")

    @classmethod
    def already_running(cls) -> StartResult:
        return cls(status="ok", message="Watch already running")

    @classmethod
    def holder_busy(cls) -> StartResult:
        return cls(
            status="holder_busy",
            message="Another watch controller holds the lock (possibly a second worker or a running CLI instance)",
        )

    @classmethod
    def error(cls, reason: str) -> StartResult:
        return cls(status="error", message=reason)


@dataclass
class WatchRuntimeStatus:
    """Authoritative in-memory runtime view for ``/api/watch/status``."""

    state: ControllerState
    last_error: str | None
    task_done: bool


class WatchController:
    """Manages the lifecycle of the autonomous watch loop in-process."""

    def __init__(
        self,
        *,
        db: DatabaseService,
        registry: BackendRegistry,
        adk_runtime: AdkRuntime,
        skill_service: SkillService,
        app_config: AppConfig,
        llm_config: LLMConfig,
        watch_config: WatchConfig,
        guardrails: GuardrailsConfig,
        notifications: NotificationsConfig,
        notifier: NotificationRouter,
    ) -> None:
        self._db = db
        self._registry = registry
        self._adk_runtime = adk_runtime
        self._skill_service = skill_service
        self._app_config = app_config
        self._llm_config = llm_config
        self._watch_config = watch_config
        self._guardrails = guardrails
        self._notifications = notifications
        self._notifier = notifier

        self._state: ControllerState = "stopped"
        self._task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        self._reload = asyncio.Event()
        self._last_error: str | None = None
        self._holder_id = uuid4().hex
        self._start_lock = asyncio.Lock()

    # ------------------------------------------------------------------ Public

    def status(self) -> WatchRuntimeStatus:
        return WatchRuntimeStatus(
            state=self._state,
            last_error=self._last_error,
            task_done=self._task is None or self._task.done(),
        )

    async def start(self) -> StartResult:
        """Spawn the supervised loop. Idempotent if already running."""
        async with self._start_lock:
            if self._state in ("starting", "running"):
                return StartResult.already_running()
            claimed = await self._db.claim_watch_holder(self._holder_id, ttl_seconds=_HOLDER_TTL_SECONDS)
            if not claimed:
                return StartResult.holder_busy()
            self._shutdown.clear()
            self._reload.clear()
            self._last_error = None
            self._state = "starting"
            self._task = asyncio.create_task(self._supervised_loop(), name="watch-loop")
            return StartResult.ok()

    async def stop(self, *, timeout: float = _STOP_TIMEOUT_DEFAULT) -> None:
        """Request graceful shutdown, cancelling if the loop exceeds ``timeout``."""
        if self._task is None:
            # Release any stale holder we might still own.
            await self._db.release_watch_holder(self._holder_id)
            return
        self._shutdown.set()
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)
        except TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        except asyncio.CancelledError:
            # Supervisor may re-raise CancelledError after cleanup — expected.
            pass
        finally:
            await self._db.release_watch_holder(self._holder_id)

    def reload(self) -> None:
        """Request a config reload at the next cycle boundary. Non-blocking."""
        self._reload.set()

    # --------------------------------------------------------------- Supervisor

    async def _supervised_loop(self) -> None:
        try:
            self._state = "running"
            await self._run_loop()
            self._state = "stopped"
        except asyncio.CancelledError:
            self._state = "stopped"
            await self._finalize_on_exit(reason="Watch loop cancelled.")
            raise
        except Exception as e:  # noqa: BLE001 — supervisor top-level guard
            logger.exception("Watch loop crashed")
            self._last_error = f"{type(e).__name__}: {e}"
            self._state = "failed"
            await self._finalize_on_exit(reason=f"Watch loop crashed: {self._last_error}")
        finally:
            await self._db.release_watch_holder(self._holder_id)
            stopped_at = datetime.now(UTC).isoformat()
            try:
                await self._db.set_watch_state("status", "stopped" if self._state != "failed" else "failed")
                await self._db.set_watch_state("stopped_at", stopped_at)
            except Exception:
                logger.debug("Failed to update watch_state during supervisor exit", exc_info=True)

    async def _finalize_on_exit(self, *, reason: str) -> None:
        """Close any half-open watch_runs/sessions if the loop aborted early."""
        try:
            await self._db.finalize_stale_watch_runs_on_boot(reason=reason)
        except Exception:
            logger.exception("Failed to finalize stale watch runs during exit")

    # ------------------------------------------------------------ Heartbeat

    async def _heartbeat_forever(self) -> None:
        """Refresh the holder lock while the loop runs."""
        try:
            while not self._shutdown.is_set():
                await asyncio.sleep(_HOLDER_HEARTBEAT_SECONDS)
                still_mine = await self._db.heartbeat_watch_holder(self._holder_id, ttl_seconds=_HOLDER_TTL_SECONDS)
                if not still_mine:
                    # Someone else claimed the lock — shut down rather than race.
                    logger.warning("Watch holder lock was reclaimed; requesting shutdown")
                    self._shutdown.set()
                    return
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------ Sleep gate

    async def _sleep_until_next_cycle(self, interval_s: float) -> None:
        """Wait up to ``interval_s`` seconds, waking on shutdown or reload."""
        shutdown_task = asyncio.create_task(self._shutdown.wait())
        reload_task = asyncio.create_task(self._reload.wait())
        try:
            done, _ = await asyncio.wait(
                {shutdown_task, reload_task},
                timeout=max(interval_s, 0.0),
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (shutdown_task, reload_task):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
        if self._reload.is_set() and not self._shutdown.is_set():
            self._reload.clear()
            await self._apply_reload()

    # ----------------------------------------------------------- Config reload

    async def _apply_reload(self) -> None:
        """Rebuild mutable configs from DB overrides and swap them into the live loop."""
        new_watch = WatchConfig()
        new_guardrails = GuardrailsConfig()
        new_notif = NotificationsConfig()

        # Update watch_config in place so closures elsewhere pick up new values.
        for field_name in WatchConfig.model_fields:
            setattr(self._watch_config, field_name, getattr(new_watch, field_name))

        # Deep-rewire notifier.
        old_notifier = self._notifier
        new_webhook = WebhookDispatcher(new_notif)
        new_email = EmailNotifier(new_notif.email) if new_notif.email and new_notif.email.enabled else None
        new_notifier = NotificationRouter(webhook=new_webhook, email=new_email, db=self._db)
        self._notifier = new_notifier
        self._notifications = new_notif
        set_notifier(new_notifier)
        if old_notifier is not None:
            try:
                await old_notifier.close()
            except Exception:
                logger.debug("Failed closing old notifier during reload", exc_info=True)

        # Deep-rewire guardrails + risk gates on the running agent.
        self._guardrails = new_guardrails
        block_notifier = new_notifier if new_watch.notify_on_blocked else None
        agent = getattr(self, "_agent", None)
        if agent is not None:
            _rewire_risk_gates(agent, app_config=self._app_config, guardrails=new_guardrails, notifier=block_notifier)

        # Push derived state onto the live session so the next cycle sees the update.
        tol = new_guardrails.watch_tolerance or new_guardrails.risk_tolerance
        session_state_template = getattr(self, "_session_state_template", None)
        if session_state_template is not None:
            session_state_template["risk_tolerance"] = tol
        session = getattr(self, "_session", None)
        if session is not None:
            session.state["risk_tolerance"] = tol
            session.state["watch_max_identical_actions_per_cycle"] = new_watch.max_identical_actions_per_cycle
            session.state["watch_max_remote_actions_per_cycle"] = new_watch.max_remote_actions_per_cycle

        await self._db.set_watch_state("interval_minutes", str(new_watch.interval_minutes))
        await self._db.set_watch_state("risk_tolerance", str(tol))
        logger.info("Reloaded watch config from DB overrides")

    # --------------------------------------------------------------- Main loop

    async def _run_loop(self) -> None:
        """The autonomous watch loop body.

        This mirrors the prior subprocess ``start_watch`` except for:
        control signals (asyncio.Event instead of DB-polled commands),
        holder heartbeat, and a bounded ``all_cycle_records`` window.
        """
        db = self._db
        watch_config = self._watch_config
        guardrails = self._guardrails
        watch_tolerance = guardrails.watch_tolerance or guardrails.risk_tolerance
        watch_allowed_tools = set(guardrails.tools_allow) | set(guardrails.watch_tools_allow)
        watch_denied_tools = set(guardrails.tools_deny) | set(guardrails.watch_tools_deny)

        emitter = WatchEventEmitter(db)
        block_notifier = self._notifier if watch_config.notify_on_blocked else None

        # Build the agent with headless risk gate(s).
        agent = _build_watch_agent(
            app_config=self._app_config,
            llm_config=self._llm_config,
            guardrails=guardrails,
            block_notifier=block_notifier,
        )
        self._agent = agent  # expose for _apply_reload to rewire risk gates

        # Build runner.
        adk_app = App(name=self._app_config.app_name, root_agent=agent)
        runner = self._adk_runtime.create_runner(app=adk_app)

        # Collect initial snapshots.
        snapshot = await _collect_all_snapshots(self._registry)
        if "local" in snapshot:
            await db.save_snapshot(snapshot["local"])

        # Create initial session.
        session_state = build_watch_session_state(
            latest_snapshot=snapshot,
            available_hosts=self._registry.host_names,
            host_configs={name: cfg.model_dump() for name, cfg in self._registry.host_configs.items()},
            risk_tolerance=watch_tolerance,
            risk_allowed_tools=watch_allowed_tools,
            risk_denied_tools=watch_denied_tools,
        )
        self._session_state_template = session_state

        session = await runner.session_service.create_session(
            app_name=self._app_config.app_name,
            user_id=self._app_config.user_id,
            state=session_state,
        )
        self._session = session
        await db.create_session(session.id)
        watch_id = f"watch_{short_uuid()}"
        watch_session_id = f"wss_{short_uuid()}"
        await db.create_watch_run(watch_id)
        await db.create_watch_session(watch_session_id, watch_id=watch_id, adk_session_id=session.id)
        emitter.set_scope(watch_id=watch_id, watch_session_id=watch_session_id)

        # Persist initial watch state.
        started_at = datetime.now(UTC).isoformat()
        for key, value in {
            "status": "running",
            "state": "running",
            "last_error": "",
            "started_at": started_at,
            "stopped_at": "",
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
        }.items():
            await db.set_watch_state(key, value)

        await dispatch(
            self._notifier,
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

        await db.cleanup_watch_data()

        cycle_count = 0
        last_cycle_error: str | None = None
        action_cooldowns: dict[str, int] = defaultdict(int)
        session_cycle_records: list[dict] = []
        all_cycle_records: list[dict] = []
        active_cycle_id: str | None = None
        active_cycle_started_at: datetime | None = None

        heartbeat_task = asyncio.create_task(self._heartbeat_forever(), name="watch-holder-heartbeat")

        try:
            while not self._shutdown.is_set():
                cycle_count += 1
                cycle_started_at = datetime.now(UTC)
                cycle_start = cycle_started_at.isoformat()
                cycle_id = f"cyc_{short_uuid()}"
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

                if self._reload.is_set():
                    self._reload.clear()
                    await self._apply_reload()
                if self._shutdown.is_set():
                    if active_cycle_id and active_cycle_started_at:
                        cancelled_cycle = await close_cancelled_cycle(
                            db,
                            cycle_id=active_cycle_id,
                            watch_session_id=watch_session_id,
                            cycle_started_at=active_cycle_started_at,
                        )
                        session_cycle_records.append(cancelled_cycle)
                        _append_bounded(all_cycle_records, cancelled_cycle)
                    active_cycle_id = None
                    active_cycle_started_at = None
                    break

                # Collect fresh snapshots.
                incidents = []
                try:
                    snapshot = await _collect_all_snapshots(self._registry)
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
                except Exception:
                    logger.debug("Snapshot collection failed", exc_info=True)

                # Build prompt with error context from previous cycle.
                prompt = watch_config.checkin_prompt
                if last_cycle_error:
                    prompt = (
                        f"Note: the previous watch cycle encountered an error: {last_cycle_error}\n"
                        "Adjust your approach if needed (e.g. skip unavailable tools).\n\n"
                        f"{prompt}"
                    )

                # Decay action cooldowns.
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
                    watch_skills = self._skill_service.list_skills(enabled_only=True, trigger="watch")
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
                            llm_config=self._llm_config,
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
                        playbook_path_counts[selection.path_taken] = (
                            playbook_path_counts.get(selection.path_taken, 0) + 1
                        )
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

                # Append watch-triggered skills.
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

                # Run the watch cycle.
                cycle_start_time = datetime.now(UTC)
                await emitter.emit_cycle_start(cycle_count, session.id, cycle_id=cycle_id)
                cycle_tool_count = 0
                cycle_input_tokens: int | None = None
                cycle_output_tokens: int | None = None
                cycle_total_tokens: int | None = None
                response_text = ""
                blocked_count = 0
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
                        run_cycle(
                            runner,
                            session,
                            agent,
                            prompt,
                            self._app_config,
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
                    await dispatch(
                        self._notifier,
                        "watch.error",
                        f"Watch cycle {cycle_count} timed out.",
                        watch_id=watch_id,
                        watch_session_id=watch_session_id,
                        cycle_id=cycle_id,
                    )
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
                    await dispatch(
                        self._notifier,
                        "watch.error",
                        f"Watch cycle {cycle_count} failed.",
                        watch_id=watch_id,
                        watch_session_id=watch_session_id,
                        cycle_id=cycle_id,
                    )
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
                cycle_carryforward = build_cycle_carryforward(outcome)
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
                _append_bounded(all_cycle_records, cycle_row)
                await persist_watch_metrics(db, outcome)
                await dispatch_outcome_notifications(
                    db,
                    self._notifier,
                    cycle_count,
                    outcome,
                    watch_id=watch_id,
                    watch_session_id=watch_session_id,
                    cycle_id=cycle_id,
                )

                if watch_config.notify_on_action and cycle_tool_count > 0 and last_cycle_error is None:
                    await dispatch(
                        self._notifier,
                        "watch.action",
                        f"Watch cycle {cycle_count} executed {cycle_tool_count} tool call(s).",
                        watch_id=watch_id,
                        watch_session_id=watch_session_id,
                        cycle_id=cycle_id,
                    )

                rotate_for_context = (
                    await session_event_count(runner, session=session, app_name=self._app_config.app_name)
                    > watch_config.max_context_events
                )
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
                    session_outcome = build_session_outcome(session_cycle_records)
                    session_report = build_session_report(
                        watch_id=watch_id,
                        watch_session_id=old_watch_session_id,
                        cycles=session_cycle_records,
                        outcome=session_outcome,
                    )
                    session_report_id = f"wsr_{short_uuid()}"
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
                        app_name=self._app_config.app_name,
                        user_id=self._app_config.user_id,
                        state=session_state,
                    )
                    self._session = session
                    await db.create_session(session.id)
                    watch_session_id = f"wss_{short_uuid()}"
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
                            app_name=self._app_config.app_name,
                            user_id=self._app_config.user_id,
                            session_id=old_session_id,
                        )
                    except Exception:
                        logger.debug("Failed to delete old session %s", old_session_id, exc_info=True)

                    await emitter.emit_session_rotated(cycle_count, old_session_id, session.id)
                    cycle_count = 0
                    session_cycle_records = []

                if cycle_count and cycle_count % 10 == 0:
                    await db.cleanup_watch_data()

                # Sleep until the next cycle (interruptible by shutdown or reload).
                await self._sleep_until_next_cycle(watch_config.interval_minutes * 60)

        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(Exception):
                await heartbeat_task

            session_outcome = build_session_outcome(session_cycle_records)
            session_report = build_session_report(
                watch_id=watch_id,
                watch_session_id=watch_session_id,
                cycles=session_cycle_records,
                outcome=session_outcome,
            )
            session_status = str(session_outcome.get("status", "error"))
            session_report_pk: int | None = None
            try:
                session_report_id = f"wsr_{short_uuid()}"
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

            watch_report = build_watch_report(
                watch_id=watch_id,
                sessions=sessions_for_report,
                cycles=all_cycle_records,
            )
            watch_report_id = f"wrp_{short_uuid()}"
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

            try:
                await dispatch(self._notifier, "watch.stop", "Squire watch mode stopped.", watch_id=watch_id)
            except Exception:
                logger.exception("Failed to dispatch watch.stop notification")
            logger.info("Watch mode stopped.")


# ---------------------------------------------------------------------- helpers


def _append_bounded(records: list[dict], row: dict) -> None:
    """Append to ``records`` and trim from the front so size stays ≤ ``_ALL_CYCLES_MAX``."""
    records.append(row)
    if len(records) > _ALL_CYCLES_MAX:
        del records[: len(records) - _ALL_CYCLES_MAX]


def _headless_risk_gate(
    tool_risk_levels: dict[str, int],
    *,
    guardrails: GuardrailsConfig,
    notifier: NotificationRouter | None,
    agent_threshold: int | None = None,
):
    """Build a headless before_tool_callback bound to the given guardrails/notifier."""
    return create_risk_gate(
        tool_risk_levels=tool_risk_levels,
        risk_overrides=dict(guardrails.tools_risk_overrides),
        default_threshold=agent_threshold,
        headless=True,
        notifier=notifier,
    )


def _rewire_risk_gates(
    agent,
    *,
    app_config: AppConfig,
    guardrails: GuardrailsConfig,
    notifier: NotificationRouter | None,
) -> None:
    """Replace ``before_tool_callback`` on the agent (and sub-agents) after a config reload."""
    if app_config.multi_agent:
        from .tools.groups import ADMIN_RISK_LEVELS, CONTAINER_RISK_LEVELS, MONITOR_RISK_LEVELS
        from .tools.notifications import NOTIFIER_RISK_LEVELS

        tolerances = {
            "Monitor": guardrails.monitor_tolerance,
            "Container": guardrails.container_tolerance,
            "Admin": guardrails.admin_tolerance,
            "Notifier": guardrails.notifier_tolerance,
        }
        risk_maps = {
            "Monitor": MONITOR_RISK_LEVELS,
            "Container": CONTAINER_RISK_LEVELS,
            "Admin": ADMIN_RISK_LEVELS,
            "Notifier": NOTIFIER_RISK_LEVELS,
        }
        for sub in getattr(agent, "sub_agents", None) or []:
            tol = tolerances.get(sub.name)
            threshold = RuleGate(threshold=tol).threshold if tol is not None else None
            sub.before_tool_callback = _headless_risk_gate(
                risk_maps.get(sub.name, TOOL_RISK_LEVELS),
                guardrails=guardrails,
                notifier=notifier,
                agent_threshold=threshold,
            )
    else:
        agent.before_tool_callback = _headless_risk_gate(
            TOOL_RISK_LEVELS,
            guardrails=guardrails,
            notifier=notifier,
        )


def _build_watch_agent(
    *,
    app_config: AppConfig,
    llm_config: LLMConfig,
    guardrails: GuardrailsConfig,
    block_notifier: NotificationRouter | None,
):
    """Build the root watch agent with the appropriate per-agent risk gates."""
    if app_config.multi_agent:
        agent_tolerances = {
            "Monitor": guardrails.monitor_tolerance,
            "Container": guardrails.container_tolerance,
            "Admin": guardrails.admin_tolerance,
            "Notifier": guardrails.notifier_tolerance,
        }

        def _per_agent_builder(agent_name: str):
            tol = agent_tolerances.get(agent_name)
            threshold = RuleGate(threshold=tol).threshold if tol is not None else None

            def factory(tool_risk_levels: dict[str, int]):
                return _headless_risk_gate(
                    tool_risk_levels,
                    guardrails=guardrails,
                    notifier=block_notifier,
                    agent_threshold=threshold,
                )

            return factory

        return create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            risk_gate_factory_builder=_per_agent_builder,
        )

    return create_squire_agent(
        app_config=app_config,
        llm_config=llm_config,
        before_tool_callback=_headless_risk_gate(
            TOOL_RISK_LEVELS,
            guardrails=guardrails,
            notifier=block_notifier,
        ),
    )


# ------------------------------------------------------------- Standalone CLI


async def run_controller_until_done(controller: WatchController) -> None:
    """Run a controller until its task completes (or a signal fires).

    Used by the ``squire watch`` CLI entrypoint — installs SIGTERM/SIGINT
    handlers that trigger ``controller.stop`` so the loop drains cleanly.
    """
    import signal

    loop = asyncio.get_running_loop()
    result = await controller.start()
    if result.status != "ok" and result.message != "Watch already running":
        raise RuntimeError(f"Failed to start watch: {result.message}")

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Received termination signal, stopping watch...")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    try:
        await _wait_for_stop_or_task(stop_event, controller)
    finally:
        await controller.stop()


async def _wait_for_stop_or_task(stop_event: asyncio.Event, controller: WatchController) -> None:
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        while controller._task is not None and not controller._task.done():
            done, _ = await asyncio.wait(
                {stop_task, controller._task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done:
                return
    finally:
        if not stop_task.done():
            stop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stop_task


async def build_controller_from_env(db: DatabaseService, registry: BackendRegistry) -> WatchController:
    """Build a WatchController wired with fresh config/singletons for the CLI path."""
    app_config = AppConfig()
    llm_config = LLMConfig()
    notif_config = NotificationsConfig()
    watch_config = WatchConfig()
    skills_config = SkillsConfig()
    guardrails = GuardrailsConfig()

    skill_service = SkillService(skills_config.path)
    adk_runtime = AdkRuntime(app_name=app_config.app_name, db_path=os.fspath(db._db_path))

    host_store = HostStore(db, registry)
    await host_store.load()

    webhook = WebhookDispatcher(notif_config)
    email = EmailNotifier(notif_config.email) if notif_config.email and notif_config.email.enabled else None
    notifier = NotificationRouter(webhook=webhook, email=email, db=db)

    return WatchController(
        db=db,
        registry=registry,
        adk_runtime=adk_runtime,
        skill_service=skill_service,
        app_config=app_config,
        llm_config=llm_config,
        watch_config=watch_config,
        guardrails=guardrails,
        notifications=notif_config,
        notifier=notifier,
    )


@contextlib.asynccontextmanager
async def controller_lifespan(controller: WatchController) -> AsyncGenerator[WatchController]:
    """Async context manager that stops the controller on exit."""
    try:
        yield controller
    finally:
        await controller.stop()
