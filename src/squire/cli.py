"""Typer CLI entry points for Squire."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="squire",
    help="Squire — an AI agent that monitors and manages your homelab.",
    no_args_is_help=True,
)


@app.command()
def chat(
    resume: Annotated[
        str | None,
        typer.Option("--resume", "-r", help="Resume a previous session by ID"),
    ] = None,
) -> None:
    """Start an interactive chat session with Squire."""
    from .main import run_chat

    run_chat(resume_session_id=resume)


@app.command()
def sessions() -> None:
    """List recent chat sessions."""
    from .main import list_sessions

    results = asyncio.run(list_sessions())

    if not results:
        typer.echo("No sessions found.")
        return

    console = Console()
    table = Table(title="Recent Sessions")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Created", style="green")
    table.add_column("Last Active", style="yellow")
    table.add_column("Preview", style="dim")

    for s in results:
        sid = s.get("session_id", "?")
        table.add_row(
            sid,
            s.get("created_at", "?")[:19],
            s.get("last_active", "?")[:19],
            (s.get("preview") or "")[:50],
        )

    console.print(table)


@app.command()
def version() -> None:
    """Show the Squire version."""
    from . import __version__

    typer.echo(f"squire {__version__}")


if __name__ == "__main__":
    app()
