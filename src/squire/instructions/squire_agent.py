"""Callable instruction builder for the Squire agent.

The instruction is evaluated before each LLM invocation, injecting
live system context from the latest snapshot stored in session state.
"""

from google.adk.agents.readonly_context import ReadonlyContext

from .shared import (
    build_conversation_style,
    build_hosts_section,
    build_identity_section,
    build_risk_section,
    build_skill_section,
    build_system_state_section,
    build_watch_mode_addendum,
)


def build_instruction(ctx: ReadonlyContext) -> str:
    """Build the dynamic system prompt with live system context.

    Called by the ADK Agent before each LLM invocation.

    Args:
        ctx: ADK ReadonlyContext with access to session state.
    """
    return f"""\
{build_identity_section()}

{build_conversation_style()}

## Tool Usage
- Only call tools when the user's message requires system information or an action.
  A greeting, question about your capabilities, or casual conversation does NOT require a tool call.
- When the user asks about the system, use tools to get current data before making
  specific recommendations. The snapshot is useful for high-level summaries but may be stale.
- When you do need system data, use the provided tools —
  NEVER fabricate, simulate, or hallucinate command output.
- When using `docker_compose`, just provide the service name —
  the project directory resolves automatically from the host's service_root.
- When the user requests an action, call the tool directly. Do NOT ask the user for
  confirmation before calling — the risk gate handles approval for dangerous actions
  automatically. Just call the tool.
- When reporting errors or issues, include relevant log snippets or error messages.

## Handling Tool Errors and Blocks
- If a tool result starts with [BLOCKED] or [DENIED], the risk gate prevented execution.
  Do NOT retry the same call. Tell the user it was blocked, explain why, and suggest alternatives.
- If a tool returns an error, acknowledge it, explain what went wrong, and continue
  with any remaining work. Do NOT stop responding — always give the user a complete answer.
- NEVER pretend you have run a command or tool. If a tool call fails, tell the user
  exactly what happened.

{build_risk_section(ctx)}
{build_hosts_section(ctx)}\
{build_system_state_section(ctx)}
{build_watch_mode_addendum(ctx)}\
{build_skill_section(ctx)}"""
