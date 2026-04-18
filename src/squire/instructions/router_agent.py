"""Instruction builder for the root Squire router agent in multi-agent mode.

The router handles greetings and casual conversation directly, and delegates
domain-specific requests to the appropriate specialist via ADK's transfer
mechanism. It carries the full conversation-style contract since it produces
the user-visible voice for non-transferred turns.
"""

from google.adk.agents.readonly_context import ReadonlyContext

from .shared import (
    build_conversation_style,
    build_hosts_section,
    build_identity_section,
    build_system_state_section,
    build_watch_mode_addendum,
)


def build_instruction(ctx: ReadonlyContext) -> str:
    """Build the router agent instruction."""
    static_block = f"""\
{build_identity_section()}

{build_conversation_style()}

## Routing
You have four specialists. Transfer to the one whose domain matches the user's request; answer yourself otherwise.

- **Monitor** — system status, health metrics, logs, config reads (read-only).
- **Container** — Docker containers, Compose stacks, images, volumes, networks.
- **Admin** — systemctl service control, shell commands (destructive risk).
- **Notifier** — send ad-hoc notifications to configured webhook endpoints.

Handle greetings, capability questions, and broad status summaries yourself —
the snapshot in your context is fresh enough.

You are one persona. A transfer is invisible to the user: the specialist continues speaking as Squire.
When routing container or host-scoped work, specialists use the same `host` across related tool calls
for one task (default `local` unless the user or prior discovery named another host).

### Example
User: "Is everything okay?"
→ Answer from the snapshot, do not transfer. E.g. "All healthy — **local** CPU 12%, 3 containers running."

User: "Restart nginx on prod-apps-01."
→ Transfer to **Container**."""

    dynamic_parts = [
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
