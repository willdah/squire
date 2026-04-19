"""Tool-output sanitization for prompt-injection defense.

Tool output (container logs, SSH stdout, command results) flows back into
the agent's LLM context. A compromised or misconfigured container can emit
text shaped like agent instructions — e.g. ``IGNORE PREVIOUS INSTRUCTIONS``
or synthetic ``<system>`` tags. This module neutralizes such content before
it reaches the model.

``sanitize_tool_output`` is the pure transform. ``create_after_tool_sanitizer``
returns an ADK ``after_tool_callback`` that wraps every tool return with the
same treatment.
"""

import re
from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B-\x1F\x7F]")

_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore\s+(?:all|any|previous|prior|above|the)\s+(?:prompts?|instructions?|rules?|context)"),
    re.compile(r"(?i)disregard\s+(?:all|any|previous|prior|above|the)\s+(?:prompts?|instructions?|rules?)"),
    re.compile(r"(?i)forget\s+(?:all|any|previous|prior|above|the)\s+(?:prompts?|instructions?|rules?)"),
    re.compile(
        r"(?i)(?:you\s+(?:are|must)\s+now|act\s+as|pretend\s+to\s+be)\s+[^\n]{0,40}(?:admin|root|system|assistant)"
    ),
    re.compile(r"<\s*/?\s*system\s*>"),
    re.compile(r"</?\s*(?:human|user|assistant)\s*>"),
    re.compile(r"(?i)---+\s*(?:user|human|system|instructions?)\s+(?:says?|prompts?)\s*---+"),
    re.compile(r"(?i)new\s+(?:system\s+)?instructions?\s*:"),
)

_DEFAULT_MAX_LENGTH = 4000


def sanitize_tool_output(
    text: Any,
    source: str = "tool",
    *,
    max_length: int = _DEFAULT_MAX_LENGTH,
) -> str:
    """Make tool output safe to feed back to the LLM.

    Strips ANSI escape sequences and control characters, neutralizes
    instruction-shaped text, and wraps the result in
    ``<tool-output source="..."></tool-output>`` tags so the model treats
    the content as untrusted data rather than in-band instructions.
    """
    if text is None:
        return f'<tool-output source="{_escape_attr(source)}"></tool-output>'

    raw = str(text)
    cleaned = _ANSI_ESCAPE_RE.sub("", raw)
    cleaned = _CONTROL_CHAR_RE.sub("", cleaned)

    for pattern in _INSTRUCTION_PATTERNS:
        cleaned = pattern.sub(_neutralize_match, cleaned)

    # Prevent embedded closing tags from breaking the wrapper.
    cleaned = cleaned.replace("</tool-output>", "<\u200btool-output/>")

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "\n[...truncated]"

    return f'<tool-output source="{_escape_attr(source)}">\n{cleaned}\n</tool-output>'


def _neutralize_match(match: re.Match[str]) -> str:
    # Never echo the original instruction-shaped string back — a downstream
    # consumer that splits on "[neutralized:" could still read the payload.
    return "[neutralized-instruction]"


def _escape_attr(value: str) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def create_after_tool_sanitizer(*, max_length: int = _DEFAULT_MAX_LENGTH):
    """Return an ADK ``after_tool_callback`` that sanitizes tool results.

    ADK's ``after_tool_callback`` is invoked after the tool returns; the
    value it returns replaces the tool's output before it is fed back to
    the model. This factory produces a callback that applies
    ``sanitize_tool_output`` to whatever string form the tool emitted.
    """

    async def _after_tool_callback(
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
        tool_response: Any,
    ) -> Any:
        if tool_response is None:
            return None
        if isinstance(tool_response, dict):
            for key in ("result", "output", "content"):
                if key in tool_response and isinstance(tool_response[key], str):
                    tool_response[key] = sanitize_tool_output(
                        tool_response[key], source=tool.name, max_length=max_length
                    )
            return tool_response
        if isinstance(tool_response, str):
            return sanitize_tool_output(tool_response, source=tool.name, max_length=max_length)
        return tool_response

    return _after_tool_callback
