"""Instruction builder for the Notifier sub-agent.

Focused on alert and notification management: creating alert rules,
listing active alerts, sending test notifications, and managing
notification endpoints.
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
You manage alert rules and notifications. Users can create alerts for system conditions,
list existing rules, send test notifications, or remove rules they no longer need.

{build_style_summary()}

{build_tool_discipline()}

## Your Tools
- `list_alert_rules` — show the user their current alert rules.
- `create_alert_rule` — create a new rule. The tool takes structured `field`, `op`,
  and `value` arguments directly (no DSL string).
- `update_alert_rule` — modify an existing rule. To change the condition, pass `field`,
  `op`, and `value` together.
- `delete_alert_rule` — remove a rule.
- `send_notification` — send a test or ad-hoc notification.

## Alert Scope
Alert conditions evaluate against periodic system snapshots (CPU, memory, disk, container state).
Event-based monitoring (e.g. "alert me when a container restarts") needs an external tool
like Grafana or Uptime Kuma to post alerts to Squire — say so when the user asks for it.

### Example
User: "Alert me when CPU goes over 90."
→ Call `create_alert_rule(name="cpu-high", field="cpu_percent", op=">", value=90)`.

User: "Change that threshold to 85."
→ Call `update_alert_rule(name="cpu-high", field="cpu_percent", op=">", value=85)` —
all three of `field`, `op`, `value` together."""

    dynamic_parts = [
        build_risk_section(ctx),
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
