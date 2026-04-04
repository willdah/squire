"""Instruction builder for the Monitor sub-agent.

Focused on read-only system observation: health checks, resource usage,
container listing, log viewing, and config reading.
"""

from google.adk.agents.readonly_context import ReadonlyContext

from .shared import (
    build_conversation_style,
    build_hosts_section,
    build_identity_section,
    build_risk_section,
    build_system_state_section,
    build_watch_mode_addendum,
)


def build_instruction(ctx: ReadonlyContext) -> str:
    """Build the Monitor agent instruction."""
    return f"""\
{build_identity_section()}

{build_conversation_style()}

## Your Role: System Monitor
You are the monitoring specialist. Your tools are read-only — you observe
the system but never modify it. Use your tools to answer questions about
system health, resource usage, container status, logs, and configuration.

## Tool Usage
- Use `system_info` for CPU, memory, disk, and uptime data.
- Use `network_info` for network interfaces, routes, and connectivity.
- Use `docker_ps` to list containers and their states.
- Use `journalctl` to view system and service logs.
- Use `read_config` to inspect configuration files.
- Only call tools when the user's message requires current system data.
  For high-level summaries, use the snapshot in your context.
- NEVER fabricate command output. If a tool fails or is blocked, report the error
  and continue with any remaining work. Do NOT stop responding.

{build_risk_section(ctx)}
{build_hosts_section(ctx)}\
{build_system_state_section(ctx)}
{build_watch_mode_addendum(ctx)}"""
