"""Callable instruction builder for the Squire agent.

The instruction is evaluated before each LLM invocation, injecting
live system context from the latest snapshot stored in session state.
"""

from .profiles import get_profile


def build_instruction(ctx) -> str:
    """Build the dynamic system prompt with live system context.

    Called by the ADK Agent before each LLM invocation.

    Args:
        ctx: ADK ReadonlyContext with access to session state.
    """
    snapshot = ctx.state.get("latest_snapshot", {})
    risk_threshold = ctx.state.get("risk_threshold", 2)
    house = ctx.state.get("house", "")
    squire_name = ctx.state.get("squire_name", "")
    profile_key = ctx.state.get("squire_profile", "")

    profile = get_profile(profile_key) if profile_key else None
    effective_name = squire_name or (profile.name if profile else "") or "Rook"

    system_context = _format_snapshot(snapshot) if snapshot else "No system snapshot available yet."
    risk_guidance = _format_risk_guidance(risk_threshold)

    identity = f"You are {effective_name}, a squire and"
    house_context = f" You are in the service of House {house}." if house else ""
    personality_block = f"\n## Personality\n{profile.personality}\n" if profile else ""

    return f"""{identity} homelab management agent.{house_context} You help users monitor, troubleshoot, and maintain their homelab infrastructure.
{personality_block}

## Conversation Style
- Match your response to the user's intent. If they greet you, greet them back. If they ask a casual question, answer conversationally. Only use tools when the user is asking about the system or requesting an action.
- When greeting or in casual conversation, respond in character with your personality. You can reference that you're keeping an eye on things without listing specifics unless asked.
- If the user asks a broad question like "how's everything?", give a brief high-level summary from the snapshot in your context. Don't call tools for this — the snapshot is recent enough.
- You are a companion, not a report generator. Don't dump system information unless asked.
- Be concise and direct in your responses.

## Tool Usage
- Only call tools when the user's message requires system information or an action. A greeting, question about your capabilities, or casual conversation does NOT require a tool call.
- When the user asks about the system, use tools to get current data before making specific recommendations. The snapshot in your context is useful for high-level summaries but may be stale for details.
- When you do need system data, use the provided tools — NEVER fabricate, simulate, or hallucinate command output.
- NEVER pretend you have run a command or tool. If a tool call is blocked or fails, say so honestly.
- For mutations (restarting containers, modifying configs), explain what you'll do and why before executing.
- If a tool call is blocked by the risk profile, inform the user and suggest alternatives.
- When reporting errors or issues, include relevant log snippets or error messages.

## Risk Threshold: {risk_threshold}/5
{risk_guidance}

## Current System State
{system_context}
"""


def _format_snapshot(snapshot: dict) -> str:
    """Format a SystemSnapshot dict into a readable summary for the system prompt."""
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

    # Disk usage
    if disks := snapshot.get("disk_usage", []):
        disk_lines = []
        for d in disks:
            mount = d.get("mount", "?")
            used = d.get("used_gb", 0)
            total = d.get("total_gb", 0)
            pct = d.get("percent", 0)
            disk_lines.append(f"  - {mount}: {used:.1f}/{total:.1f} GB ({pct:.0f}%)")
        parts.append("**Disks**:\n" + "\n".join(disk_lines))

    # Containers
    if containers := snapshot.get("containers", []):
        container_lines = []
        for c in containers:
            name = c.get("name", "?")
            state = c.get("state", "?")
            image = c.get("image", "?")
            container_lines.append(f"  - {name}: {state} ({image})")
        parts.append(f"**Containers** ({len(containers)}):\n" + "\n".join(container_lines))

    return "\n".join(parts) if parts else "System information not yet collected."


def _format_risk_guidance(threshold: int) -> str:
    """Return guidance text based on the active risk threshold."""
    from agent_risk_engine import RiskLevel

    level_label = RiskLevel(threshold).label if 1 <= threshold <= 5 else "Custom"
    return (
        f"Your risk threshold is set to {threshold}/5 ({level_label}). "
        f"Tools at risk level {threshold} or below run automatically. "
        f"Tools above level {threshold} require user approval before execution. "
        f"Some tools may be individually overridden (always allowed, always prompted, or denied)."
    )
