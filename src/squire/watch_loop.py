"""Pure loop-body helpers for watch mode.

Extracted from ``squire.watch`` so the in-process ``WatchController`` can
compose them without carrying the whole module. No behavioral changes —
signatures and return shapes are preserved from the prior subprocess
implementation.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from google.adk.runners import Runner
from google.genai import types

from .database.service import DatabaseService
from .notifications.router import NotificationRouter
from .tokens import coalesce_token_count, extract_token_usage_from_event
from .watch_autonomy import action_signature
from .watch_emitter import WatchEventEmitter

if TYPE_CHECKING:
    from .config import AppConfig

logger = logging.getLogger(__name__)


def short_uuid() -> str:
    return uuid4().hex[:12]


def extract_token_usage(event) -> tuple[int | None, int | None, int | None]:
    """Provider-reported token counts from a watch-cycle event."""
    return extract_token_usage_from_event(event)


def accumulate_token_count(current: int | None, event_value: int | None) -> int | None:
    """Track the latest non-null token usage in a cycle."""
    return coalesce_token_count(current, event_value)


def build_cycle_carryforward(outcome: dict) -> dict:
    """Compact tactical memory that can be injected into the next cycle."""
    return {
        "status": outcome.get("cycle_status", "unknown"),
        "incident_key": outcome.get("incident_fingerprint"),
        "actions": str(outcome.get("actions", ""))[:400],
        "verification": str(outcome.get("verification", ""))[:400],
        "watchouts": str(outcome.get("escalation", ""))[:300],
    }


async def close_cancelled_cycle(
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
        cycle_carryforward=build_cycle_carryforward(outcome),
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


def build_session_outcome(cycles: list[dict]) -> dict:
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


def build_session_report(*, watch_id: str, watch_session_id: str, cycles: list[dict], outcome: dict) -> dict:
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


def build_watch_report(*, watch_id: str, sessions: list[dict], cycles: list[dict]) -> dict:
    """Create watch-completion rollup for operators.

    ``cycles`` may be a bounded window of the most recent cycles; the report
    notes the window size so operators know the figures are not lifetime totals
    when a long-running watch rotates many sessions.
    """
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


async def run_cycle(
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
        event_input_tokens, event_output_tokens, event_total_tokens = extract_token_usage(event)
        input_tokens = accumulate_token_count(input_tokens, event_input_tokens)
        output_tokens = accumulate_token_count(output_tokens, event_output_tokens)
        total_tokens = accumulate_token_count(total_tokens, event_total_tokens)

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


async def session_event_count(runner: Runner, *, session, app_name: str) -> int:
    """Best-effort event count using the durable session service."""
    try:
        fresh = await runner.session_service.get_session(
            app_name=app_name,
            user_id=session.user_id,
            session_id=session.id,
        )
        if fresh is not None:
            events = getattr(fresh, "events", None)
            if isinstance(events, list):
                return len(events)
    except Exception:
        logger.debug("Failed to fetch session for event count", exc_info=True)

    events = getattr(session, "events", None)
    if isinstance(events, list):
        return len(events)
    return 0


async def dispatch(
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


async def persist_watch_metrics(db: DatabaseService, outcome: dict) -> None:
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


async def dispatch_outcome_notifications(
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
            await dispatch(
                notifier,
                "watch.incident_detected",
                f"Cycle {cycle}: detected {incident_count} incident(s) ({incident_fingerprint}).",
                watch_id=watch_id,
                watch_session_id=watch_session_id,
                cycle_id=cycle_id,
            )
            await db.set_watch_state("last_notified_incident", incident_fingerprint)
    if int(outcome.get("tool_count", 0)) > 0:
        await dispatch(
            notifier,
            "watch.remediation",
            f"Cycle {cycle}: executed {outcome.get('tool_count', 0)} remediation action(s).",
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )
    if outcome.get("resolved"):
        await dispatch(
            notifier,
            "watch.verification",
            f"Cycle {cycle}: remediation verified as resolved.",
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )
    if outcome.get("escalated"):
        await dispatch(
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
        await dispatch(
            notifier,
            "watch.digest",
            summary,
            watch_id=watch_id,
            watch_session_id=watch_session_id,
            cycle_id=cycle_id,
        )


def configure_logging() -> None:
    """Configure structured logging for watch CLI to stdout.

    Only invoked by ``squire watch`` (standalone CLI); in-process the FastAPI
    server owns the root logger.
    """
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
