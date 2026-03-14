"""Approval modal — modal dialog for risk approval prompts in the TUI."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ApprovalModal(ModalScreen[bool]):
    """Modal dialog that asks the user to approve or deny a tool execution.

    Returns True if approved, False if denied.
    """

    DEFAULT_CSS = """
    ApprovalModal {
        align: center middle;
    }

    #approval-dialog {
        width: 60;
        max-width: 80%;
        height: auto;
        max-height: 80%;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }

    #approval-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #approval-tool-name {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    #approval-args {
        color: $text-muted;
        margin-bottom: 1;
        max-height: 10;
        overflow-y: auto;
    }

    #approval-risk {
        color: $warning;
        text-style: italic;
        margin-bottom: 1;
    }

    #approval-buttons {
        margin-top: 1;
        align: center middle;
        height: auto;
    }

    #approval-buttons Button {
        margin: 0 2;
    }

    #btn-approve {
        background: $success;
    }

    #btn-deny {
        background: $error;
    }
    """

    def __init__(self, tool_name: str, tool_args: dict, risk_level: int, **kwargs):
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._risk_level = risk_level

    def compose(self) -> ComposeResult:
        args_display = "\n".join(f"  {k}: {v}" for k, v in self._tool_args.items()) if self._tool_args else "  (none)"

        with Vertical(id="approval-dialog"):
            yield Label("Tool Approval Required", id="approval-title")
            yield Static(f"Tool: [bold]{self._tool_name}[/bold]", id="approval-tool-name")
            yield Static(f"Arguments:\n{args_display}", id="approval-args")
            from agent_risk_engine import RiskLevel

            level_label = RiskLevel(self._risk_level).label if 1 <= self._risk_level <= 5 else str(self._risk_level)
            yield Static(f"Risk level: {level_label} ({self._risk_level}/5)", id="approval-risk")
            with Horizontal(id="approval-buttons"):
                yield Button("Approve", variant="success", id="btn-approve")
                yield Button("Deny", variant="error", id="btn-deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-approve")
