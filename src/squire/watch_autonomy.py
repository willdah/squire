"""Autonomy helpers for watch mode lifecycle and outcome tracking."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

INCIDENT_FAMILY_CATALOG: dict[str, str] = {
    "container-unhealthy:": "Container is unhealthy/restarting/dead/exited.",
    "disk-pressure:": "Disk usage is critically high.",
    "disk-warning:": "Disk usage is elevated.",
    "host-unreachable:": "Host snapshot could not be collected.",
}


@dataclass(slots=True)
class Incident:
    """Detected incident from snapshot telemetry."""

    key: str
    severity: str
    title: str
    detail: str
    host: str = "local"


def detect_incidents(snapshot: dict[str, dict]) -> list[Incident]:
    """Detect high-value incidents from multi-host snapshot data."""
    incidents: list[Incident] = []

    for host, host_snapshot in snapshot.items():
        error = (host_snapshot or {}).get("error")
        if error:
            incidents.append(
                Incident(
                    key=f"host-unreachable:{host}",
                    severity="high",
                    title="Host unreachable",
                    detail=str(error),
                    host=host,
                )
            )
            continue

        disk_raw = str((host_snapshot or {}).get("disk_usage_raw", ""))
        disk_percent = _extract_max_percent(disk_raw)
        if disk_percent >= 90:
            incidents.append(
                Incident(
                    key=f"disk-pressure:{host}",
                    severity="high",
                    title="Disk pressure",
                    detail=f"Observed disk usage at {disk_percent:.0f}%",
                    host=host,
                )
            )
        elif disk_percent >= 80:
            incidents.append(
                Incident(
                    key=f"disk-warning:{host}",
                    severity="medium",
                    title="Disk usage warning",
                    detail=f"Observed disk usage at {disk_percent:.0f}%",
                    host=host,
                )
            )

        for container in (host_snapshot or {}).get("containers", []) or []:
            state = str(container.get("state", "")).lower()
            status = str(container.get("status", "")).lower()
            name = str(container.get("name", "unknown"))
            if any(flag in state for flag in ("restarting", "dead", "exited")) or "unhealthy" in status:
                incidents.append(
                    Incident(
                        key=f"container-unhealthy:{host}:{name}",
                        severity="high",
                        title="Container unhealthy",
                        detail=f"{name} is in state='{state or status}'",
                        host=host,
                    )
                )

    return incidents


def build_cycle_contract_prompt(
    base_prompt: str,
    incidents: list[Incident],
    playbook_instructions: list[str],
    blocked_signatures: list[str],
) -> str:
    """Compose a strict contract prompt for autonomous watch cycles."""
    sections = [base_prompt.strip()]
    sections.append(
        "You are operating in strict autonomous watch mode. Follow this exact lifecycle:\n"
        "1) Detect incidents and prioritize by severity.\n"
        "2) Produce RCA hypotheses with confidence.\n"
        "3) Execute only bounded, low-blast-radius remediation actions.\n"
        "4) Verify outcomes with fresh checks.\n"
        "5) Escalate unresolved issues with explicit reason."
    )
    if incidents:
        lines = [f"- [{inc.severity}] {inc.title} ({inc.host}) :: {inc.detail}" for inc in incidents]
        sections.append("Detected incidents:\n" + "\n".join(lines))
    else:
        sections.append("Detected incidents:\n- none; run proactive health checks and report status.")

    if playbook_instructions:
        sections.append("Autonomous playbooks to apply (only when relevant):\n" + "\n\n".join(playbook_instructions))

    if blocked_signatures:
        blocked = "\n".join(f"- {signature}" for signature in blocked_signatures)
        sections.append(
            "Do not repeat these recent actions (cooldown active):\n"
            f"{blocked}\n"
            "Choose lower-risk alternatives or escalate."
        )

    sections.append(
        "Format your final response with these sections:\n"
        "## Incident Summary\n"
        "## RCA Hypotheses\n"
        "## Action Plan and Actions Taken\n"
        "## Verification Results\n"
        "## Escalation"
    )
    return "\n\n".join(sections)


def parse_contract_sections(text: str) -> dict[str, str]:
    """Extract canonical contract sections from markdown response text."""
    pattern = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)
    headers = list(pattern.finditer(text))
    if not headers:
        return {}

    sections: dict[str, str] = {}
    for idx, match in enumerate(headers):
        title = match.group(1).strip().lower()
        start = match.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        sections[title] = text[start:end].strip()
    return sections


def build_cycle_outcome(
    incidents: list[Incident],
    sections: dict[str, str],
    *,
    tool_count: int,
    blocked_count: int,
    cycle_status: str,
) -> dict:
    """Build structured cycle outcome for persistence and UI."""
    escalation = sections.get("escalation", "")
    verification = sections.get("verification results", "")
    action_text = sections.get("action plan and actions taken", "")

    resolved = bool(verification) and "unresolved" not in verification.lower() and "failed" not in verification.lower()
    escalated = bool(escalation) and not _is_non_escalation_text(escalation)
    issue_key = dominant_incident_key(incidents)

    return {
        "incident_count": len(incidents),
        "incident_key": issue_key,
        "resolved": resolved and cycle_status == "ok",
        "escalated": escalated or cycle_status != "ok",
        "blocked_count": blocked_count,
        "tool_count": tool_count,
        "cycle_status": cycle_status,
        "rca": sections.get("rca hypotheses", "")[:600],
        "verification": verification[:600],
        "actions": action_text[:600],
        "escalation": escalation[:600],
    }


def dominant_incident_key(incidents: list[Incident]) -> str | None:
    """Stable key for deduplicating repeated notifications."""
    if not incidents:
        return None
    ordered = sorted(inc.key for inc in incidents)
    raw = "|".join(ordered)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def action_signature(tool_name: str, args: dict) -> str:
    """Normalize a tool call into a short stable signature."""
    focus = {
        "action": args.get("action"),
        "host": args.get("host", "local"),
        "name": args.get("name"),
        "service": args.get("service"),
        "container": args.get("container"),
        "stack": args.get("stack"),
        "command": args.get("command"),
    }
    encoded = json.dumps(focus, sort_keys=True, default=str)
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:10]
    return f"{tool_name}:{digest}"


def _extract_max_percent(disk_usage_raw: str) -> float:
    matches = re.findall(r"(\d{1,3})%", disk_usage_raw)
    if not matches:
        return 0.0
    return max(float(m) for m in matches)


def _is_non_escalation_text(text: str) -> bool:
    """Return True when escalation text explicitly means no escalation needed."""
    normalized = re.sub(r"[*_`>#-]", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip(" .:")
    if not normalized:
        return True

    markers = (
        "none",
        "n/a",
        "na",
        "no escalation",
        "not required",
        "not needed",
        "no further action",
    )
    if normalized in markers:
        return True
    return any(normalized.startswith(f"{marker} ") or normalized.startswith(f"{marker}:") for marker in markers)


def severity_rank(severity: str) -> int:
    """Sort helper for deterministic incident ordering."""
    ranks = {"high": 0, "medium": 1, "low": 2}
    return ranks.get(severity.lower(), 3)
