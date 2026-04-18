"""Instruction builder for the Monitor sub-agent.

Focused on read-only system observation: health checks, resource usage,
container listing, log viewing, and config reading. All Monitor tools are
at risk level 1, so the risk-tolerance section is deliberately omitted —
nothing here can ever trip the gate.
"""

from google.adk.agents.readonly_context import ReadonlyContext

from .shared import (
    build_hosts_section,
    build_identity_section,
    build_style_summary,
    build_system_state_section,
    build_tool_discipline,
    build_watch_mode_addendum,
)


def build_instruction(ctx: ReadonlyContext) -> str:
    """Build the Monitor agent instruction."""
    static_block = f"""\
{build_identity_section()}

## Scope
You handle read-only system observation: health, resource usage, container state, logs, and configuration.

{build_style_summary()}

{build_tool_discipline()}

## Your Tools
- `system_info` — CPU, memory, disk, uptime.
- `network_info` — network interfaces, routes, connectivity.
- `docker_ps` — list containers and their states.
- `journalctl` — system and service logs.
- `read_config` — inspect configuration files."""

    dynamic_parts = [
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
