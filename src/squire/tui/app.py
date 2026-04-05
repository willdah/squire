"""Squire TUI — Textual application with chat pane and status panels."""

import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Footer, Header

from .approval_bridge import ApprovalBridge, ApprovalRequest
from .approval_modal import ApprovalModal, ConfirmModal
from .chat_pane import ChatPane
from .log_viewer import LogViewer
from .status_panel import StatusPanel

SQUIRE_THEME = Theme(
    name="squire-dark",
    primary="#8931c4",
    secondary="#5b257e",
    accent="#e08a3a",
    warning="#f0ad4e",
    error="#b41c2b",
    success="#009f42",
    foreground="#c6c6c6",
    background="#2a1838",
    surface="#382348",
    panel="#451f5e",
    dark=True,
)


class SquireApp(App):
    """Main Textual application for Squire."""

    SUB_TITLE = "Homelab Agent"
    CSS = """
    #main-container {
        height: 1fr;
    }

    #status-panel {
        width: 30;
        min-width: 25;
        border-right: solid $primary;
    }

    #right-column {
        width: 1fr;
        layout: vertical;
    }

    #chat-pane {
        height: 2fr;
    }

    #log-viewer {
        height: 1fr;
        border-top: solid $primary;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+g", "toggle_log", "Log", show=True),
        Binding("ctrl+s", "toggle_status", "Status", show=True),
        Binding("ctrl+x", "clear_all_sessions", "Del Sessions", show=True),
    ]

    def __init__(
        self,
        agent_runner=None,
        session=None,
        app_config=None,
        db=None,
        notifier=None,
        initial_snapshot=None,
        prior_messages=None,
        approval_bridge: ApprovalBridge | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._agent_runner = agent_runner
        self._session = session
        self._app_config = app_config
        self._squire_name = "Squire"
        self.title = "Squire"
        self._db = db
        self._notifier = notifier
        self._initial_snapshot = initial_snapshot
        self._prior_messages = prior_messages
        self._approval_bridge = approval_bridge

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield StatusPanel(id="status-panel")
            with Vertical(id="right-column"):
                yield ChatPane(
                    agent_runner=self._agent_runner,
                    session=self._session,
                    app_config=self._app_config,
                    db=self._db,
                    notifier=self._notifier,
                    squire_name=self._squire_name,
                    id="chat-pane",
                )
                yield LogViewer(id="log-viewer")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(SQUIRE_THEME)
        self.theme = "squire-dark"

        # Register this app with the approval bridge
        if self._approval_bridge:
            self._approval_bridge.set_app(self)

        if self._initial_snapshot:
            status_panel = self.query_one(StatusPanel)
            status_panel.update_snapshot(self._initial_snapshot)

        # Restore prior messages if resuming a session
        if self._prior_messages:
            chat_pane = self.query_one(ChatPane)
            chat_pane.restore_messages(self._prior_messages)

    def show_approval_modal(self, request: ApprovalRequest) -> None:
        """Show the approval modal for a pending tool execution.

        Called from the approval bridge via call_from_thread.
        """
        modal = ApprovalModal(
            tool_name=request.tool_name,
            tool_args=request.args,
            risk_level=request.risk_level,
        )

        def on_dismiss(approved: bool) -> None:
            request.set_result(approved)

        self.push_screen(modal, callback=on_dismiss)

    def update_status_snapshot(self, snapshot: dict) -> None:
        """Update the status panel with a new snapshot (called from background task)."""
        try:
            status_panel = self.query_one(StatusPanel)
            status_panel.update_snapshot(snapshot)
        except Exception:
            logging.getLogger(__name__).debug("Failed to update status snapshot", exc_info=True)

    def add_log_entry(self, text: str, category: str = "event") -> None:
        """Add an entry to the log viewer panel."""
        try:
            log_viewer = self.query_one(LogViewer)
            log_viewer.add_entry(text, category=category)
        except Exception:
            logging.getLogger(__name__).debug("Failed to add log entry", exc_info=True)

    def action_toggle_log(self) -> None:
        log_viewer = self.query_one(LogViewer)
        log_viewer.display = not log_viewer.display

    def action_toggle_status(self) -> None:
        status_panel = self.query_one(StatusPanel)
        status_panel.display = not status_panel.display

    def action_clear_chat(self) -> None:
        chat_pane = self.query_one(ChatPane)
        chat_pane.clear_messages()

    async def action_clear_all_sessions(self) -> None:
        """Prompt the user to confirm deleting all sessions, then delete them."""
        confirmed = await self.push_screen_wait(
            ConfirmModal(
                message="Delete ALL sessions and their messages?\nThis cannot be undone.",
                title="Clear All Sessions",
            )
        )
        if confirmed and self._db is not None:
            count = await self._db.delete_all_sessions()
            self.notify(f"Deleted {count} session(s).", severity="information")
