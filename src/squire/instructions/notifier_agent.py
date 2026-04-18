"""Instruction builder for the Notifier sub-agent.

Focused on ad-hoc notification dispatch. Alerting is delegated to external
monitoring stacks (Prometheus/Alertmanager, Grafana, Uptime Kuma), which
should post alerts into Squire via webhooks when the ingestion surface lands.
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
    """Build the Notifier agent instruction."""
    static_block = f"""\
{build_identity_section()}

## Scope
You dispatch ad-hoc notifications to configured webhook endpoints. Users may ask you
to send a test message, notify a channel about a finding, or relay a status update.

{build_style_summary()}

{build_tool_discipline()}

## Your Tools
- `send_notification` — deliver a message via the configured webhook channels.
  Accepts a `message` and optional `category` (default `"user"`).

## Scope Boundary
Squire does not host its own alert-rule engine. If the user asks for threshold-based
alerting, point them at their existing monitoring stack (Grafana / Alertmanager /
Uptime Kuma / Zabbix) — those systems decide *when* to alert; Squire is the place to
reason about *how to respond*."""

    dynamic_parts = [
        build_risk_section(ctx),
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
