"""Shared type aliases used across the Squire codebase."""

from collections.abc import Callable
from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

# ADK before_tool_callback signature
BeforeToolCallback = Callable[[BaseTool, dict[str, Any], ToolContext], Any]

# Factory that creates a scoped BeforeToolCallback from a tool risk levels dict
RiskGateFactory = Callable[[dict[str, int]], BeforeToolCallback]

# Builder that returns a per-agent RiskGateFactory given the agent name
RiskGateFactoryBuilder = Callable[[str], RiskGateFactory]
