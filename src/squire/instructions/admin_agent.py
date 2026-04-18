"""Instruction builder for the Admin sub-agent.

Focused on system administration: managing systemd services and executing
shell commands. These are the highest-risk tools in Squire, so the prompt
carries an explicit pre-action reasoning step.
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
    """Build the Admin agent instruction."""
    static_block = f"""\
{build_identity_section()}

## Scope
You handle system-level administration: systemd services and shell commands.
These operations can affect host stability, so reason briefly before acting.

{build_style_summary()}

{build_tool_discipline()}

## Your Tools
- `systemctl` — manage systemd services (start, stop, restart, status, enable, disable).
- `run_command` — execute arbitrary shell commands. Subject to allowlist/denylist
  configured by the user; on a denial, suggest an alternative.

## Before Acting
Before stopping, restarting, or running a destructive command: note in one sentence which
services or clients depend on the target and whether a narrower action (restart a single unit,
target a single service) is safer than a broad one. Then call the tool.

### Example
User: "Restart the web stack."
→ Think: "nginx and the app container both depend on redis; a `systemctl restart nginx` is
narrower than restarting the whole stack." Then call `systemctl(action='restart', unit='nginx')`."""

    dynamic_parts = [
        build_risk_section(ctx),
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
