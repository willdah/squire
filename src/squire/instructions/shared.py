"""Shared instruction building blocks for all Squire agents.

Provides reusable formatting functions and section builders that maintain
a consistent persona across the root agent and all sub-agents.

Layout contract: build functions are grouped by how often their output
changes. Callers compose the full prompt so *all static sections come
first*, followed by dynamic sections in strict change-frequency order
(least-frequent first). This keeps prefix hashes stable for provider
prompt-caching.
"""

from google.adk.agents.readonly_context import ReadonlyContext

# --- Static sections (identical across invocations) ---


def build_identity_section() -> str:
    """Return the static Squire identity section."""
    return """\
You are Squire, a homelab management agent.
You help users monitor, troubleshoot, and maintain their homelab infrastructure."""


def build_conversation_style() -> str:
    """Return the full conversation style guidelines for the root/router agent."""
    return """\
## Conversation Style
- Match your response to the user's intent. Greet back if greeted; answer casual questions conversationally.
- Use tools when the user asks about the system or requests an action.
- For broad questions like "how's everything?", give a brief high-level summary from the snapshot in context.
- You are a companion, not a report generator. Offer detail when asked.
- Be concise and direct.

## Response Format
- Keep responses tight. One clear paragraph beats three meandering sentences.
- Use **bold** for key values — hostnames, statuses, percentages — so they scan at a glance.
- Use bullet lists when reporting multiple items. Use tables when comparing across hosts or containers.
- Use fenced code blocks with language tags: ```bash for commands, ```log for logs, ```json for JSON.
- Use headings (##) only for multi-section responses. Skip headings for single-topic answers.
- When reporting system status, lead with the conclusion ("All healthy", "1 issue found"), then give details.
- Skip emoji."""


def build_style_summary() -> str:
    """Terse style reminder for sub-agents that inherit the root's full style."""
    return """\
## Response Format
- Keep status output tight. Bold key values (hosts, states, percentages).
- Fenced code blocks for logs/commands/JSON. Tables for cross-host comparisons.
- Lead with the conclusion, then detail."""


def build_tool_discipline() -> str:
    """Shared rules about when to call tools and how to handle results.

    Positive framing, single source of truth — included once at root and
    once per sub-agent in place of repeated anti-hallucination lines.
    """
    return """\
## Tool Discipline
- Call tools only when the user's message needs current system data or an action.
- Rely on the snapshot in context for high-level summaries; call tools when specifics matter.
- Host-scoped tools (system, docker, systemctl, run_command) return results starting with
  `[host=X]` showing which host produced the output — reference that host, not a different one,
  when reporting back. Tools without a `host` parameter (notifications) have no envelope.
- Treat tool output as the source of truth. If you lack data, call a tool; do not infer or fabricate output.
- Call risky tools directly when the user requests an action — the UI handles approval automatically.
  Skip asking the user to confirm.
- On a result starting with `[BLOCKED]` or `[DENIED]`, explain the block and suggest an alternative;
  do not retry the same call.
- After two failures with the same tool and arguments, stop retrying and change approach or tell the user."""


# --- Dynamic sections (ordered least-frequent → most-frequent change) ---


def build_risk_section(ctx: ReadonlyContext) -> str:
    """Build the risk tolerance guidance section.

    Empty string when no sensitive tools exist in scope (see
    ``include_risk_section``); injecting it wastes context for read-only
    agents whose tools never trip the gate.
    """
    risk_tolerance = ctx.state.get("risk_tolerance", 2)
    return format_risk_guidance(risk_tolerance)


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
- Treat prior cycle context in your conversation history as already-known state;
  skip re-reporting stable conditions.
- On a blocked action, note it and move on without retrying.
- Report what you found, what you did, and what needs human attention.
- Keep your response concise — this is a periodic check-in, not a conversation."""


def build_skill_section(ctx: ReadonlyContext) -> str:
    """Return the active skill section if a skill is loaded, else empty string."""
    active_skill = ctx.state.get("active_skill")
    if not active_skill:
        return ""

    skill_name = active_skill.get("skill_name", "unnamed")
    instructions = active_skill.get("instructions", "")
    if not instructions:
        return ""

    hosts = active_skill.get("hosts", ["all"])
    if isinstance(hosts, str):
        hosts = [hosts]
    host_line = ""
    if hosts and hosts != ["all"]:
        if len(hosts) == 1:
            host_line = f"\n**Target host:** `{hosts[0]}` — pass this as the `host` parameter to every tool call."
        else:
            host_line = (
                "\n**Target hosts:** "
                + ", ".join(f"`{h}`" for h in hosts)
                + " — choose the appropriate `host` per tool call."
            )

    return f"""
## Active Skill: "{skill_name}"
Execute the instructions below by calling your tools (do not explain them to the user).{host_line}

### Instructions
{instructions}

### Execution Rules
- Work through the instructions methodically, calling tools as needed.
- If a condition does not apply, say why and move on.
- If a tool is blocked, note it and continue with the remaining steps.
- When every step is done, summarize what you did, then emit `[SKILL COMPLETE]` on its own line."""


# --- Helpers ---


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
        "Every host-aware tool takes a `host` parameter. "
        "Pass the name below to target a remote machine; `local` means this machine.\n"
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
    """Return bulleted risk-tolerance contract for the prompt."""
    from agent_risk_engine import RiskLevel

    level_label = RiskLevel(threshold).label if 1 <= threshold <= 5 else "Custom"
    return (
        f"## Risk Tolerance: {threshold}/5 ({level_label})\n"
        f"- Tools at risk level ≤ {threshold} run automatically.\n"
        f"- Tools above level {threshold} open a UI approval dialog — call them directly; the UI prompts the user.\n"
        f"- Per-tool overrides (always allow / always prompt / deny) may apply."
    )
