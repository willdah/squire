"""Shared instruction building blocks for all Squire agents.

Provides reusable formatting functions and section builders that maintain
a consistent persona across the root agent and all sub-agents.
"""

from google.adk.agents.readonly_context import ReadonlyContext


def build_identity_section() -> str:
    """Return the static Squire identity section."""
    return """\
You are Squire, a homelab management agent.
You help users monitor, troubleshoot, and maintain their homelab infrastructure."""


def build_conversation_style() -> str:
    """Return the conversation style guidelines."""
    return """\
## Conversation Style
- Match your response to the user's intent. If they greet you, greet them back.
  If they ask a casual question, answer conversationally.
  Only use tools when the user is asking about the system or requesting an action.
- When greeting or in casual conversation, respond naturally and conversationally.
  You can reference that you're keeping an eye on things without listing specifics unless asked.
- If the user asks a broad question like "how's everything?", give a brief high-level
  summary from the snapshot in your context. Don't call tools — the snapshot is recent enough.
- You are a companion, not a report generator. Don't dump system information unless asked.
- Be concise and direct in your responses.

## Response Format
- Keep responses tight. One clear paragraph beats three meandering sentences.
- Use **bold** for key values — hostnames, statuses, percentages — so they scan at a glance.
- Use bullet lists when reporting multiple items. Use tables when comparing across hosts or containers.
- Use fenced code blocks with language tags: \`\`\`bash for commands, \`\`\`log for logs, \`\`\`json for JSON.
- Use headings (##) only for multi-section responses. A single-topic answer needs no heading.
- When reporting system status, lead with the conclusion ("All healthy", "1 issue found"), then give details.
- Never use emoji in responses."""


def build_risk_section(ctx: ReadonlyContext) -> str:
    """Build the risk tolerance guidance section."""
    risk_tolerance = ctx.state.get("risk_tolerance", 2)
    return f"""\
## Risk Tolerance: {risk_tolerance}/5
{format_risk_guidance(risk_tolerance)}"""


def build_hosts_section(ctx: ReadonlyContext) -> str:
    """Build the available hosts section from the live registry.

    Reads directly from the BackendRegistry so newly enrolled hosts
    are visible immediately, even in an existing chat session.
    """
    available_hosts, host_configs = _load_hosts_from_registry()
    return format_hosts_section(available_hosts, host_configs)


def build_system_state_section(ctx: ReadonlyContext) -> str:
    """Build the current system state section from the latest snapshot."""
    snapshot = ctx.state.get("latest_snapshot", {})
    system_context = format_snapshot(snapshot) if snapshot else "No system snapshot available yet."
    return f"## Current System State\n{system_context}"


def build_skill_section(ctx: ReadonlyContext) -> str:
    """Return the active skill section if a skill is loaded, else empty string."""
    active_skill = ctx.state.get("active_skill")
    if not active_skill:
        return ""

    skill_name = active_skill.get("skill_name", "unnamed")
    instructions = active_skill.get("instructions", "")
    if not instructions:
        return ""

    host = active_skill.get("host", "all")
    host_line = ""
    if host != "all":
        host_line = f"\n**Target host:** `{host}` — pass this as the `host` parameter to every tool call."

    return f"""
## Active Skill: "{skill_name}"
You are executing a skill. Follow the instructions below.{host_line}

### Instructions
{instructions}

### Execution Rules
- You MUST execute the instructions by calling your tools. Do NOT tell the user how to do it.
- Work through the instructions methodically, calling tools as needed.
- If a condition doesn't apply, explain why and move on.
- If a tool call is blocked, note it and continue.
- When you have completed all instructions, provide a summary, then emit [SKILL COMPLETE]."""


def build_watch_mode_addendum(ctx: ReadonlyContext) -> str:
    """Return watch-mode instructions if watch_mode is active, else empty string."""
    if not ctx.state.get("watch_mode"):
        return ""
    return """
## Autonomous Watch Mode
You are running autonomously — no human is in the loop.
- Review the current system state and act on anything that needs attention.
- Prioritize: container health > service availability > resource usage.
- Be targeted with tool calls — only call tools when you have a specific reason.
- Do NOT retry failed actions. If a tool is blocked, note it and move on.
- Report what you found, what you did, and what needs human attention.
- Keep your response concise — this is a periodic check-in, not a conversation."""


def _load_hosts_from_registry() -> tuple[list[str], dict]:
    """Load host information from the live BackendRegistry.

    Returns the current host list and configs, reflecting any hosts
    added or removed at runtime via HostStore.
    """
    try:
        from ..tools._registry import get_registry

        registry = get_registry()
        available = registry.host_names
        configs = {name: cfg.model_dump() for name, cfg in registry.host_configs.items()}
        return available, configs
    except Exception:
        return ["local"], {}


# --- Formatting helpers ---


def format_snapshot(snapshot: dict) -> str:
    """Format a snapshot dict into a readable summary for the system prompt.

    Accepts either a single-host dict (legacy) or a multi-host dict keyed by host name.
    """
    if snapshot and all(isinstance(v, dict) for v in snapshot.values()):
        parts = []
        for host_name, host_snapshot in snapshot.items():
            label = f"### {host_name}"
            if host_snapshot.get("error"):
                parts.append(f"{label}\n*{host_snapshot['error']}*")
            else:
                parts.append(f"{label}\n{_format_single_host_snapshot(host_snapshot)}")
        return "\n\n".join(parts) if parts else "System information not yet collected."

    return _format_single_host_snapshot(snapshot)


def _format_single_host_snapshot(snapshot: dict) -> str:
    """Format a single host's snapshot dict into a readable summary."""
    parts = []

    if hostname := snapshot.get("hostname"):
        parts.append(f"**Host**: {hostname}")

    if os_info := snapshot.get("os_info"):
        parts.append(f"**OS**: {os_info}")

    cpu = snapshot.get("cpu_percent", 0)
    mem_used = snapshot.get("memory_used_mb", 0)
    mem_total = snapshot.get("memory_total_mb", 0)
    if mem_total > 0:
        parts.append(f"**CPU**: {cpu:.1f}% | **Memory**: {mem_used:.0f}/{mem_total:.0f} MB")

    uptime = snapshot.get("uptime_seconds", 0)
    if uptime > 0:
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        parts.append(f"**Uptime**: {hours}h {minutes}m")

    if disks := snapshot.get("disk_usage", []):
        disk_lines = []
        for d in disks:
            mount = d.get("mount", "?")
            used = d.get("used_gb", 0)
            total = d.get("total_gb", 0)
            pct = d.get("percent", 0)
            disk_lines.append(f"  - {mount}: {used:.1f}/{total:.1f} GB ({pct:.0f}%)")
        parts.append("**Disks**:\n" + "\n".join(disk_lines))

    if containers := snapshot.get("containers", []):
        container_lines = []
        for c in containers:
            name = c.get("name", "?")
            state = c.get("state", "?")
            image = c.get("image", "?")
            container_lines.append(f"  - {name}: {state} ({image})")
        parts.append(f"**Containers** ({len(containers)}):\n" + "\n".join(container_lines))

    return "\n".join(parts) if parts else "No data available."


def format_hosts_section(available_hosts: list[str], host_configs: dict) -> str:
    """Format the available hosts section for the system prompt."""
    if len(available_hosts) <= 1:
        return ""

    lines = ["## Available Hosts"]
    lines.append(
        "Every tool accepts an optional `host` parameter. "
        "Use the host name below to target a remote machine. "
        "Default is `local` (this machine).\n"
    )
    for name in available_hosts:
        if name == "local":
            lines.append("- `local` — this machine")
        else:
            cfg = host_configs.get(name, {})
            addr = cfg.get("address", "?")
            tags = cfg.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            services = cfg.get("services", [])
            service_root = cfg.get("service_root", "/opt")
            lines.append(f"- `{name}` — {addr}{tag_str}")
            if services:
                lines.append(f"  - Services ({service_root}): {', '.join(services)}")

    lines.append("")
    return "\n".join(lines) + "\n"


def format_risk_guidance(threshold: int) -> str:
    """Return guidance text based on the active risk tolerance."""
    from agent_risk_engine import RiskLevel

    level_label = RiskLevel(threshold).label if 1 <= threshold <= 5 else "Custom"
    return (
        f"Your risk tolerance is set to {threshold}/5 ({level_label}). "
        f"Tools at risk level {threshold} or below run automatically. "
        f"Tools above level {threshold} require user approval via a UI dialog — "
        f"you do NOT need to ask the user for confirmation yourself. Just call the tool. "
        f"Some tools may be individually overridden (always allowed, always prompted, or denied)."
    )
