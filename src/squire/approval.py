"""Approval provider protocol — frontend-agnostic interface for tool approval.

Any frontend (TUI, web server, CLI) can implement ApprovalProvider to
handle tool approval requests from the risk gate callback.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ApprovalProvider(Protocol):
    """Protocol for requesting user approval of a tool execution.

    Implementations must be thread-safe — the risk gate callback runs
    inside an ADK worker thread, not the main event loop.
    """

    def request_approval(self, tool_name: str, args: dict[str, Any], risk_level: int) -> bool:
        """Request approval for a tool execution.

        Args:
            tool_name: Name of the tool requesting approval.
            args: Arguments that will be passed to the tool.
            risk_level: Assessed risk level (1-5).

        Returns:
            True if approved, False if denied.
        """
        ...


class DenyAllApproval:
    """ApprovalProvider that denies all requests.

    Used in headless/watch mode where no human is in the loop.
    """

    def request_approval(self, tool_name: str, args: dict[str, Any], risk_level: int) -> bool:
        return False
