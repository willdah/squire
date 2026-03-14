"""Status panel — system status sidebar for the Squire TUI.

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
            snapshot: Either a single-host snapshot dict or a multi-host dict
                keyed by host name.
        """
        content = self.query_one("#status-content")
        content.remove_children()

        # Detect multi-host snapshot
        if snapshot and all(isinstance(v, dict) for v in snapshot.values()):
            sections = []
            for host_name, host_snapshot in snapshot.items():
                sections.append(self._format_host(host_name, host_snapshot))
            display_text = "\n\n".join(sections) if sections else "No data yet."
        else:
            # Legacy single-host snapshot
            display_text = self._format_host("local", snapshot)

        content.mount(Static(display_text, classes="status-section"))

    @staticmethod
    def _format_host(host_name: str, snapshot: dict) -> str:
        """Format a single host's snapshot for the status panel."""
        parts = []

        if snapshot.get("error"):
            parts.append(f"[bold]{host_name}:[/bold] [red]{snapshot['error']}[/red]")
            return "\n".join(parts)

        hostname = snapshot.get("hostname", host_name)
        parts.append(f"[bold]{hostname}:[/bold]")

        cpu = snapshot.get("cpu_percent", 0)
        mem_used = snapshot.get("memory_used_mb", 0)
        mem_total = snapshot.get("memory_total_mb", 0)
        if mem_total > 0:
            parts.append(f"  CPU: {cpu:.1f}% | Mem: {mem_used:.0f}/{mem_total:.0f}MB")

        if containers := snapshot.get("containers", []):
            running = sum(1 for c in containers if c.get("state") == "running")
            parts.append(f"  Containers: {running}/{len(containers)}")
            for c in containers[:10]:
                icon = "+" if c.get("state") == "running" else "-"
                parts.append(f"    {icon} {c.get('name', '?')}")

        return "\n".join(parts) if parts else f"[bold]{host_name}:[/bold] No data."
