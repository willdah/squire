"""Approval bridge — thread-safe link between the ADK risk gate callback and the TUI.

The risk gate callback runs inside a Textual worker thread. When it needs
user approval, it posts an approval request to the Textual app (which runs
on the main thread) and blocks until the user responds via the modal.

Implements the ApprovalProvider protocol for use with the risk gate factory.
"""

import threading
from typing import Any


class ApprovalRequest:
    """A pending approval request with a threading event for synchronization."""

    def __init__(self, tool_name: str, args: dict[str, Any], risk_level: int):
        self.tool_name = tool_name
        self.args = args
        self.risk_level = risk_level
        self._event = threading.Event()
        self._approved = False

    def set_result(self, approved: bool) -> None:
        """Set the approval result and unblock the waiting thread."""
        self._approved = approved
        self._event.set()

    def wait(self, timeout: float = 120.0) -> bool:
        """Block until the user responds or timeout expires.

        Returns True if approved, False if denied or timed out.
        """
        self._event.wait(timeout=timeout)
        return self._approved


class ApprovalBridge:
    """Thread-safe bridge between the risk gate callback and the TUI.

    Satisfies the ApprovalProvider protocol. Instantiated in main.py
    and passed to the risk gate factory via closure.
    """

    def __init__(self):
        self._app = None  # Set to the Textual App instance on startup

    def set_app(self, app) -> None:
        """Register the Textual app for posting approval requests."""
        self._app = app

    def request_approval(self, tool_name: str, args: dict[str, Any], risk_level: int) -> bool:
        """Request user approval for a tool execution.

        Called from the worker thread (inside the ADK agent loop).
        Blocks until the user responds in the TUI.

        Returns True if approved, False if denied.
        """
        if not self._app:
            return False

        request = ApprovalRequest(tool_name, args, risk_level)

        # Post to the Textual app's main thread
        self._app.call_from_thread(self._app.show_approval_modal, request)

        # Block until the user responds
        return request.wait()
