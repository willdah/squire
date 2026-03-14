"""Renew TUI — Textual application with chat pane and status panels."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header

from .approval_bridge import ApprovalRequest, approval_bridge
from .approval_modal import ApprovalModal
from .chat_pane import ChatPane
from .status_panel import StatusPanel


class RenewApp(App):
    """Main Textual application for Renew."""

    TITLE = "Renew"
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

    #chat-pane {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
    ]

    def __init__(self, agent_runner=None, session=None, app_config=None, initial_snapshot=None, **kwargs):
        super().__init__(**kwargs)
        self._agent_runner = agent_runner
        self._session = session
        self._app_config = app_config
        self._initial_snapshot = initial_snapshot

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield StatusPanel(id="status-panel")
            yield ChatPane(
                agent_runner=self._agent_runner,
                session=self._session,
                app_config=self._app_config,
                id="chat-pane",
            )
        yield Footer()

    def on_mount(self) -> None:
        # Register this app with the approval bridge
        approval_bridge.set_app(self)

        if self._initial_snapshot:
            status_panel = self.query_one(StatusPanel)
            status_panel.update_snapshot(self._initial_snapshot)

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

    def action_clear_chat(self) -> None:
        chat_pane = self.query_one(ChatPane)
        chat_pane.clear_messages()
