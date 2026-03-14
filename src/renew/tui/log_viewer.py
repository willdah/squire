"""Log viewer — scrollable panel for tool output and system events."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class LogEntry(Static):
    """A single log entry in the viewer."""

    DEFAULT_CSS = """
    LogEntry {
        margin: 0 1;
        padding: 0 1;
    }

    LogEntry.tool-call {
        color: $warning;
    }

    LogEntry.tool-result {
        color: $text-muted;
    }

    LogEntry.event {
        color: $accent;
    }

    LogEntry.error {
        color: $error;
    }
    """

    def __init__(self, content: str, category: str = "event", **kwargs):
        super().__init__(content, **kwargs)
        self.add_class(category)


class LogViewer(Static):
    """Scrollable log/tool-output viewer panel."""

    DEFAULT_CSS = """
    LogViewer {
        layout: vertical;
        padding: 0;
    }

    .log-header {
        text-style: bold;
        color: $primary;
        padding: 1;
    }

    #log-content {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    MAX_ENTRIES = 200

    def compose(self) -> ComposeResult:
        yield Static("Activity Log", classes="log-header")
        yield VerticalScroll(id="log-content")

    def add_entry(self, text: str, category: str = "event") -> None:
        """Append a log entry and auto-scroll to bottom.

        Args:
            text: The log text to display.
            category: One of "tool-call", "tool-result", "event", "error".
        """
        log_content = self.query_one("#log-content")
        log_content.mount(LogEntry(text, category=category))
        log_content.scroll_end(animate=False)

        # Trim old entries to prevent unbounded growth
        children = list(log_content.children)
        if len(children) > self.MAX_ENTRIES:
            for child in children[: len(children) - self.MAX_ENTRIES]:
                child.remove()

    def clear(self) -> None:
        """Remove all log entries."""
        self.query_one("#log-content").remove_children()
