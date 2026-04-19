"""Proactive insight sweep — metrics + observe-tier skills.

Two sources populate the ``insights`` table:

1. **Metric rules** (``watch_autonomy.insight_sweep_from_metrics``) — deterministic
   observations derived from existing telemetry (auto-resolve rate, rate ceiling
   hits, audit chain state, approval latency).

2. **Skills** — enabled skills with ``autonomy=observe`` and a recognized
   ``category`` are run as prompts against the LLM, no write tools attached.
   Skills produce ``INSIGHT:`` lines in their response that this module parses
   and upserts.

The scheduler in ``api.app`` calls :func:`run_insight_sweep` on a cadence
configured by ``watch.insight_sweep_interval_hours`` (default 6h).

### Skill output contract

An observe-tier skill emits zero or more lines of the form::

    INSIGHT: severity=medium summary="Backup freshness degraded on web-01" host="web-01"

Recognized fields (all lowercase):

- ``severity`` (required) — ``low``, ``medium``, ``high``, ``critical``
- ``summary`` (required) — one-line actionable statement
- ``detail`` (optional) — longer explanation
- ``host`` (optional) — host the insight applies to
- ``category`` (optional) — overrides the skill's own category if set

Values may be wrapped in double quotes to include spaces.
"""

from __future__ import annotations

import logging
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)

_VALID_CATEGORIES: frozenset[str] = frozenset({"reliability", "maintenance", "security", "design"})
_VALID_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})

# --- Parser ---------------------------------------------------------------


def parse_skill_insights(response_text: str, *, default_category: str) -> list[dict[str, Any]]:
    """Parse ``INSIGHT:`` lines from a skill response into structured records."""
    insights: list[dict[str, Any]] = []
    if not response_text:
        return insights
    for raw_line in response_text.splitlines():
        line = raw_line.strip().lstrip("-*").strip()
        if not line.upper().startswith("INSIGHT:"):
            continue
        payload = line[len("INSIGHT:") :].strip()
        fields = _parse_fields(payload)
        summary = fields.get("summary", "").strip()
        severity = fields.get("severity", "").strip().lower()
        if not summary or severity not in _VALID_SEVERITIES:
            continue
        category = fields.get("category", default_category).strip().lower()
        if category not in _VALID_CATEGORIES:
            category = default_category
        insights.append(
            {
                "category": category,
                "severity": severity,
                "summary": summary,
                "detail": (fields.get("detail") or "").strip() or None,
                "host": (fields.get("host") or "").strip() or None,
            }
        )
    return insights


def _parse_fields(line: str) -> dict[str, str]:
    """Parse space-separated ``key=value`` pairs with optional quoted values."""
    fields: dict[str, str] = {}
    i = 0
    n = len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        key_start = i
        while i < n and (line[i].isalnum() or line[i] == "_"):
            i += 1
        if i == key_start or i >= n or line[i] != "=":
            # Malformed — skip to next whitespace.
            while i < n and not line[i].isspace():
                i += 1
            continue
        key = line[key_start:i].lower()
        i += 1  # consume '='
        if i < n and line[i] == '"':
            i += 1
            value_start = i
            while i < n and line[i] != '"':
                i += 1
            value = line[value_start:i]
            if i < n:
                i += 1  # consume closing quote
        else:
            value_start = i
            while i < n:
                if line[i].isspace():
                    j = i
                    while j < n and line[j].isspace():
                        j += 1
                    if j < n and (line[j].isalnum() or line[j] == "_"):
                        k = j
                        while k < n and (line[k].isalnum() or line[k] == "_"):
                            k += 1
                        if k < n and line[k] == "=":
                            break
                i += 1
            value = line[value_start:i].strip()
        fields[key] = value
    return fields


# --- Scheduler + runner --------------------------------------------------


async def run_insight_sweep(
    *,
    db,
    skill_service=None,
    adk_runtime=None,
    llm_config=None,
    app_config=None,
) -> dict[str, int]:
    """Run both metric and skill-driven sweeps; return counts by source."""
    from .watch_autonomy import insight_sweep_from_metrics

    metric_insights = await insight_sweep_from_metrics(db)
    skill_insights = 0
    if skill_service is not None and adk_runtime is not None and llm_config is not None and app_config is not None:
        try:
            skill_insights = await _run_skill_driven_sweep(
                db=db,
                skill_service=skill_service,
                adk_runtime=adk_runtime,
                llm_config=llm_config,
                app_config=app_config,
            )
        except Exception:
            logger.exception("Skill-driven insight sweep failed")

    return {"metric_insights": metric_insights, "skill_insights": skill_insights}


async def _run_skill_driven_sweep(
    *,
    db,
    skill_service,
    adk_runtime,
    llm_config,
    app_config,
) -> int:
    """Run each enabled observe-tier categorized skill and upsert insights."""
    skills = skill_service.list_skills(enabled_only=True)
    candidates = [s for s in skills if s.autonomy == "observe" and s.category in _VALID_CATEGORIES]
    if not candidates:
        return 0

    # Build a lightweight insight agent once, reuse across skills.
    agent = _build_insight_agent(app_config, llm_config)
    app_obj = _build_app(agent)
    runner = adk_runtime.create_runner(app=app_obj)

    total = 0
    for skill in candidates:
        try:
            count = await _run_one_skill(
                skill=skill,
                runner=runner,
                adk_runtime=adk_runtime,
                app_config=app_config,
                db=db,
            )
        except Exception:
            logger.exception("Insight skill '%s' failed", skill.name)
            continue
        total += count

    return total


def _build_insight_agent(app_config, llm_config):
    """Agent with no tools — skill reasons over the snapshot provided in context."""
    from google.adk.agents.llm_agent import Agent
    from google.adk.models.lite_llm import LiteLlm

    model_kwargs: dict[str, Any] = {}
    if llm_config.api_base:
        model_kwargs["api_base"] = llm_config.api_base

    return Agent(
        name="Insights",
        model=LiteLlm(model=llm_config.model, **model_kwargs),
        instruction=_INSIGHT_SYSTEM_PROMPT,
        tools=[],
        generate_content_config=types.GenerateContentConfig(
            temperature=llm_config.temperature,
            max_output_tokens=llm_config.max_tokens,
        ),
    )


def _build_app(agent):
    from google.adk.apps import App

    return App(name="squire_insights", root_agent=agent)


_INSIGHT_SYSTEM_PROMPT = """You are Squire's insight sweeper.

You observe a homelab's current state and emit proactive insights the user can act on.
You do NOT have tools; reason over the context provided in the user message.

When you produce insights, emit each as its own line in this exact format:

INSIGHT: severity=<low|medium|high|critical> summary="<short statement>" detail="<optional>" host="<optional>"

Rules:
- Only emit INSIGHT: lines for observations that are clearly supported by the context.
- If nothing noteworthy is found, emit no INSIGHT lines.
- Do not fabricate hosts, versions, or metrics. When unsure, do not emit.
- Prefer fewer, higher-signal insights over many low-value ones.
"""


async def _run_one_skill(
    *,
    skill,
    runner,
    adk_runtime,
    app_config,
    db,
) -> int:
    """Execute a single observe-tier skill, parse its response, upsert insights."""
    # Deterministic session id so sweeps reuse history.
    session_id = f"insight-sweep-{skill.name}"
    session = await adk_runtime.get_or_create_session(
        app_name="squire_insights",
        user_id=app_config.user_id,
        session_id=session_id,
        state={"insight_skill": skill.name},
    )

    # Pull latest snapshot + recent metrics as context.
    latest_snapshot = await _fetch_latest_snapshot(db)
    metrics = await db.get_watch_metrics(hours=24)

    prompt_parts: list[str] = [
        f"# Skill: {skill.name}",
        f"Category: {skill.category}",
        f"Description: {skill.description}" if skill.description else "",
        "",
        "## Skill instructions",
        skill.instructions.strip(),
        "",
        "## Current context",
        f"Latest snapshot (hosts): {sorted(latest_snapshot)}",
        f"Auto-resolve rate (24h): {int((metrics['auto_resolve_rate'] or 0) * 100)}%",
        f"Total resolved (24h): {metrics['total_resolved']}",
        f"Rate-ceiling hits (24h): {metrics['rate_limit_hits']}",
        "",
        (
            "Produce zero or more INSIGHT: lines following the format specified in "
            "your system prompt. Do NOT include any other structured output."
        ),
    ]
    prompt = "\n".join(p for p in prompt_parts if p is not None)

    response_text = await _collect_response(
        runner=runner,
        session=session,
        app_config=app_config,
        prompt=prompt,
    )

    records = parse_skill_insights(response_text, default_category=skill.category or "reliability")
    for record in records:
        await db.upsert_insight(
            category=record["category"],
            host=record.get("host"),
            summary=record["summary"],
            detail=record.get("detail"),
            severity=record.get("severity"),
        )
    return len(records)


async def _collect_response(*, runner, session, app_config, prompt: str) -> str:
    message = types.Content(parts=[types.Part(text=prompt)])
    parts: list[str] = []
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
            if getattr(part, "text", None):
                parts.append(part.text)
    return "".join(parts)


async def _fetch_latest_snapshot(db) -> dict[str, Any]:
    """Best-effort read of the most recent snapshot, keyed by host name."""
    try:
        from .api.app import get_latest_snapshot
    except Exception:
        return {}
    try:
        return await get_latest_snapshot()
    except Exception:
        return {}
