"""Instruction builder for the root Squire router agent in multi-agent mode.

The router handles greetings and casual conversation directly, and delegates
domain-specific requests to the appropriate sub-agent via ADK's transfer mechanism.
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
    return f"""\
{build_identity_section()}

{build_conversation_style()}

## Routing
You have specialist agents that handle domain-specific tasks. Transfer to
the appropriate specialist when the user's request falls within their domain.
Handle greetings, casual conversation, and general questions yourself —
do NOT transfer for simple interactions.

You are one persona. When you transfer to a specialist, the user should not
notice any change in voice or personality. The specialists share your identity.
When routing container or host-scoped work, specialists must use the same `host`
parameter across related tool calls for one task (default is `local` unless the user
or prior discovery named another host).

{build_hosts_section(ctx)}\
{build_system_state_section(ctx)}
{build_watch_mode_addendum(ctx)}"""
