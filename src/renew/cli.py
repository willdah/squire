"""Typer CLI entry points for Renew."""

from typing import Annotated

import typer

app = typer.Typer(
    name="renew",
    help="Renew — an AI agent that monitors and manages your homelab.",
    no_args_is_help=True,
)


@app.command()
def chat(
    resume: Annotated[
        str | None,
        typer.Option("--resume", "-r", help="Resume a previous session by ID"),
    ] = None,
) -> None:
    """Start an interactive chat session with Renew."""
    from .main import run_chat

    run_chat(resume_session_id=resume)


@app.command()
def version() -> None:
    """Show the Renew version."""
    from . import __version__

    typer.echo(f"renew {__version__}")


if __name__ == "__main__":
    app()
