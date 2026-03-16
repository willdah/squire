"""Alerts panel — read-only display of active alert rules in the TUI."""

from textual.widgets import Static


class AlertsPanel(Static):
    """Read-only panel showing active alert rules and their status."""

    DEFAULT_CSS = """
    AlertsPanel {
        padding: 1;
        height: auto;
        max-height: 15;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("No alert rules configured.", **kwargs)
        self._rules: list[dict] = []

    def update_rules(self, rules: list[dict]) -> None:
        """Update the displayed alert rules."""
        self._rules = rules
        if not rules:
            self.update("No alert rules configured.")
            return

        lines = [f"[bold]Alert Rules[/bold] ({len(rules)})"]
        for r in rules:
            status = "[green]on[/green]" if r.get("enabled") else "[dim]off[/dim]"
            severity = r.get("severity", "warning")
            sev_style = {"critical": "red", "warning": "yellow", "info": "blue"}.get(severity, "white")
            lines.append(
                f"  {status} [{sev_style}]{r['name']}[/{sev_style}]: "
                f"{r['condition']} ({r.get('host', 'all')})"
            )

        self.update("\n".join(lines))
