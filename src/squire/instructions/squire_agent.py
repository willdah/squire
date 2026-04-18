"""Callable instruction builder for the Squire agent (single-agent mode).

The instruction is evaluated before each LLM invocation, injecting
live system context from the latest snapshot stored in session state.

Layout: all static sections first (cache-stable prefix), then dynamic
sections ordered by change-frequency (least frequent first).
"""

from google.adk.agents.readonly_context import ReadonlyContext

from .shared import (
    build_conversation_style,
    build_hosts_section,
    build_identity_section,
    build_risk_section,
    build_skill_section,
    build_system_state_section,
    build_tool_discipline,
    build_watch_mode_addendum,
)


def build_instruction(ctx: ReadonlyContext) -> str:
    """Build the dynamic system prompt with live system context.

    Called by the ADK Agent before each LLM invocation.

    Args:
        ctx: ADK ReadonlyContext with access to session state.
    """
    static_block = f"""\
{build_identity_section()}

{build_conversation_style()}

{build_tool_discipline()}

## Docker Compose
When calling `docker_compose`, pass just the service name —
the project directory resolves from the host's `service_root`."""

    # Dynamic sections — strictly ordered by change frequency so prompt
    # caches remain stable across unrelated changes.
    dynamic_parts = [
        build_risk_section(ctx),
        build_hosts_section(ctx),
        build_system_state_section(ctx),
        build_watch_mode_addendum(ctx),
        build_skill_section(ctx),
    ]
    dynamic_block = "\n\n".join(part for part in dynamic_parts if part)

    return f"{static_block}\n\n{dynamic_block}" if dynamic_block else static_block
