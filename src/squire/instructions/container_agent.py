"""Instruction builder for the Container sub-agent.

Focused on container lifecycle management: viewing logs, restarting
services, and managing Docker Compose stacks.
"""

from google.adk.agents.readonly_context import ReadonlyContext

from .shared import (
    build_hosts_section,
    build_identity_section,
    build_risk_section,
    build_style_summary,
    build_system_state_section,
    build_tool_discipline,
    build_watch_mode_addendum,
)


def build_instruction(ctx: ReadonlyContext) -> str:
    """Build the Container agent instruction."""
    static_block = f"""\
{build_identity_section()}

## Scope
You handle container lifecycle: viewing logs, managing containers, pulling images,
cleaning up resources, and managing Docker Compose stacks.

{build_style_summary()}

{build_tool_discipline()}

## Your Tools
- `docker_ps` — list containers; use this to confirm which `host` runs Docker before follow-up actions.
- `docker_logs` — view container logs for troubleshooting.
- `docker_compose` — manage Compose stacks (start, stop, restart, pull, up, down).
  Pass just the service name; the project directory resolves from the host's `service_root`.
- `docker_container` — manage individual containers (inspect, start, stop, restart, remove).
- `docker_image` — manage images (list, inspect, pull, remove).
- `docker_volume` — manage volumes (list, inspect).
- `docker_network` — manage networks (list, inspect).
- `docker_cleanup` — check disk usage and prune unused resources."""

    dynamic_parts = [
        build_risk_section(ctx),
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
