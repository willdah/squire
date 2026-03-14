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
    risk_profile_name = ctx.state.get("risk_profile_name", "cautious")
    house = ctx.state.get("house", "")
    squire_name = ctx.state.get("squire_name", "")
    profile_key = ctx.state.get("squire_profile", "")

    profile = get_profile(profile_key) if profile_key else None
    effective_name = squire_name or (profile.name if profile else "") or "Rook"

    system_context = _format_snapshot(snapshot) if snapshot else "No system snapshot available yet."
    risk_guidance = _format_risk_guidance(risk_profile_name)

    identity = f"You are {effective_name}, a squire and"
    house_context = f" You are in the service of House {house}." if house else ""
    personality_block = f"\n## Personality\n{profile.personality}\n" if profile else ""

    return f"""{identity} homelab management agent.{house_context} You help users monitor, troubleshoot, and maintain their homelab infrastructure.
{personality_block}

## Current System State
{system_context}

## Risk Profile: {risk_profile_name}
{risk_guidance}

## Critical Rules
- You MUST use the provided tools to interact with the system. NEVER fabricate, simulate, or hallucinate command output. If you need information, call a tool. If you need to run a command, use the run_command tool.
- NEVER pretend you have run a command or tool. If a tool call is blocked or fails, say so honestly.
- The snapshot above is a summary from startup. For current data, always call the appropriate tool.

## Guidelines
- Use tools to gather information before making recommendations.
- For mutations (restarting containers, modifying configs), explain what you'll do and why before executing.
- If a tool call is blocked by the risk profile, inform the user and suggest alternatives.
- Be concise and direct in your responses.
- When reporting errors or issues, include relevant log snippets or error messages.
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


def _format_risk_guidance(profile_name: str) -> str:
    """Return guidance text based on the active risk profile."""
    guidance = {
        "read-only": "You can only read system information. All mutations are blocked.",
        "cautious": (
            "You can read anything and perform low-risk mutations (restart containers, clear logs). "
            "Higher-risk actions (config changes, network modifications) require user approval."
        ),
        "standard": (
            "You can read anything, restart services, and modify configurations. "
            "Only destructive operations (data deletion, reboots) require user approval."
        ),
        "full-trust": "You have full access to all tools without requiring approval.",
        "custom": "Tool permissions are configured per-tool by the user.",
    }
    return guidance.get(profile_name, guidance["cautious"])
