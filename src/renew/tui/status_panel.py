"""Status panel — system status sidebar for the Renew TUI.

Displays container states, CPU/memory/disk gauges, and network info.
In Phase 4 this will be driven by live snapshot data.
"""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class StatusPanel(Static):
    """Sidebar showing system status overview."""

    DEFAULT_CSS = """
    StatusPanel {
        layout: vertical;
        padding: 1;
    }

    .status-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .status-section {
        margin-bottom: 1;
    }

    .status-placeholder {
        color: $text-muted;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("System Status", classes="status-header")
        yield VerticalScroll(
            Static("Waiting for snapshot...", classes="status-placeholder"),
            id="status-content",
        )

    def update_snapshot(self, snapshot: dict) -> None:
        """Update the status panel with fresh snapshot data.

        Args:
            snapshot: A SystemSnapshot dict.
        """
        content = self.query_one("#status-content")
        content.remove_children()

        parts = []

        if hostname := snapshot.get("hostname"):
            parts.append(f"[bold]Host:[/bold] {hostname}")

        cpu = snapshot.get("cpu_percent", 0)
        mem_used = snapshot.get("memory_used_mb", 0)
        mem_total = snapshot.get("memory_total_mb", 0)
        if mem_total > 0:
            parts.append(f"[bold]CPU:[/bold] {cpu:.1f}%")
            parts.append(f"[bold]Mem:[/bold] {mem_used:.0f}/{mem_total:.0f}MB")

        if containers := snapshot.get("containers", []):
            running = sum(1 for c in containers if c.get("state") == "running")
            parts.append(f"\n[bold]Containers:[/bold] {running}/{len(containers)}")
            for c in containers[:10]:
                icon = "+" if c.get("state") == "running" else "-"
                parts.append(f"  {icon} {c.get('name', '?')}")

        display_text = "\n".join(parts) if parts else "No data yet."
        content.mount(Static(display_text, classes="status-section"))
