"""Shared type aliases used across the Squire codebase."""

from typing import Any, Callable

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

# ADK before_tool_callback signature
BeforeToolCallback = Callable[[BaseTool, dict[str, Any], ToolContext], Any]

# Factory that creates a scoped BeforeToolCallback from a tool risk levels dict
RiskGateFactory = Callable[[dict[str, int]], BeforeToolCallback]
