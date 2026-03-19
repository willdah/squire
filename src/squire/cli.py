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


sessions_app = typer.Typer(name="sessions", help="Manage chat sessions.")
app.add_typer(sessions_app)


@sessions_app.command("list")
def sessions_list() -> None:
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


@sessions_app.command("clear")
def sessions_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete all chat sessions and their messages."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService

    if not yes and not typer.confirm("Delete ALL sessions and their messages? This cannot be undone."):
        raise typer.Abort()

    async def _run() -> int:
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        try:
            return await db.delete_all_sessions()
        finally:
            await db.close()

    count = asyncio.run(_run())
    typer.echo(f"Deleted {count} session(s).")


watch_app = typer.Typer(name="watch", help="Autonomous watch mode.", invoke_without_command=True)
app.add_typer(watch_app)


@watch_app.callback()
def watch_default(ctx: typer.Context) -> None:
    """Start autonomous watch mode — monitor and tend systems continuously."""
    if ctx.invoked_subcommand is not None:
        return
    from .watch import run_watch

    run_watch()


@watch_app.command("status")
def watch_status() -> None:
    """Show the current watch mode status."""
    from .watch import get_watch_status

    state = asyncio.run(get_watch_status())

    if not state:
        typer.echo("Watch mode has not run yet (no state found).")
        return

    console = Console()
    status = state.get("status", "unknown")
    style = "green" if status == "running" else "red" if status == "stopped" else "yellow"

    console.print(f"[bold]Watch Mode Status:[/bold] [{style}]{status}[/{style}]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    if started := state.get("started_at"):
        table.add_row("Started", started[:19])
    if stopped := state.get("stopped_at"):
        table.add_row("Stopped", stopped[:19])
    if cycle := state.get("cycle"):
        table.add_row("Current cycle", cycle)
    if last_cycle := state.get("last_cycle_at"):
        table.add_row("Last cycle", last_cycle[:19])
    if interval := state.get("interval_minutes"):
        table.add_row("Interval", f"{interval}m")
    if threshold := state.get("risk_tolerance"):
        table.add_row("Risk threshold", threshold)
    if session_id := state.get("session_id"):
        table.add_row("Session", session_id[:12] + "...")

    console.print(table)

    if last_response := state.get("last_response"):
        console.print()
        console.print("[bold]Last response:[/bold]")
        console.print(f"  {last_response[:300]}")


@app.command()
def web(
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on")] = 8420,
    host: Annotated[str, typer.Option("--host", "-H", help="Host to bind to")] = "0.0.0.0",
    reload: Annotated[bool, typer.Option("--reload", help="Enable auto-reload for development")] = False,
) -> None:
    """Start the Squire web interface."""
    import uvicorn

    uvicorn.run(
        "squire.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def version() -> None:
    """Show the Squire version."""
    from . import __version__

    typer.echo(f"squire {__version__}")


# --- Alert rule management ---

alerts_app = typer.Typer(name="alerts", help="Manage alert rules.")
app.add_typer(alerts_app)


@alerts_app.command("list")
def alerts_list() -> None:
    """List all configured alert rules."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        try:
            return await db.list_alert_rules()
        finally:
            await db.close()

    rules = asyncio.run(_run())

    if not rules:
        typer.echo("No alert rules configured.")
        return

    console = Console()
    table = Table(title="Alert Rules")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Condition", style="white")
    table.add_column("Host", style="blue")
    table.add_column("Severity", style="yellow")
    table.add_column("Cooldown", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Last Fired", style="dim")

    for r in rules:
        status = "enabled" if r.get("enabled") else "disabled"
        last = (r.get("last_fired_at") or "never")[:19]
        table.add_row(
            r["name"],
            r["condition"],
            r.get("host", "all"),
            r.get("severity", "warning"),
            f"{r.get('cooldown_minutes', 30)}m",
            status,
            last,
        )

    console.print(table)


@alerts_app.command("add")
def alerts_add(
    name: Annotated[str, typer.Option("--name", "-n", help="Rule name")],
    condition: Annotated[str, typer.Option("--condition", "-c", help="Condition (e.g., 'cpu_percent > 90')")],
    host: Annotated[str, typer.Option("--host", help="Host to monitor ('all' or specific name)")] = "all",
    severity: Annotated[str, typer.Option("--severity", "-s", help="info, warning, or critical")] = "warning",
    cooldown: Annotated[int, typer.Option("--cooldown", help="Cooldown in minutes")] = 30,
) -> None:
    """Add a new alert rule."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .notifications.conditions import ConditionError, parse_condition

    # Validate condition syntax
    try:
        parse_condition(condition)
    except ConditionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if severity not in ("info", "warning", "critical"):
        typer.echo("Error: severity must be 'info', 'warning', or 'critical'.", err=True)
        raise typer.Exit(1)

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        try:
            return await db.save_alert_rule(
                name=name,
                condition=condition,
                host=host,
                severity=severity,
                cooldown_minutes=cooldown,
            )
        finally:
            await db.close()

    try:
        rule_id = asyncio.run(_run())
        typer.echo(f"Alert rule '{name}' created (id={rule_id}).")
    except Exception as e:
        if "UNIQUE" in str(e):
            typer.echo(f"Error: a rule named '{name}' already exists.", err=True)
        else:
            typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@alerts_app.command("remove")
def alerts_remove(
    name: Annotated[str, typer.Argument(help="Name of the alert rule to remove")],
) -> None:
    """Remove an alert rule by name."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        try:
            return await db.delete_alert_rule(name)
        finally:
            await db.close()

    deleted = asyncio.run(_run())
    if deleted:
        typer.echo(f"Alert rule '{name}' removed.")
    else:
        typer.echo(f"Error: no rule named '{name}' found.", err=True)
        raise typer.Exit(1)


@alerts_app.command("enable")
def alerts_enable(
    name: Annotated[str, typer.Argument(help="Name of the alert rule to enable")],
) -> None:
    """Enable an alert rule."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        try:
            return await db.update_alert_rule(name, enabled=1)
        finally:
            await db.close()

    updated = asyncio.run(_run())
    if updated:
        typer.echo(f"Alert rule '{name}' enabled.")
    else:
        typer.echo(f"Error: no rule named '{name}' found.", err=True)
        raise typer.Exit(1)


@alerts_app.command("disable")
def alerts_disable(
    name: Annotated[str, typer.Argument(help="Name of the alert rule to disable")],
) -> None:
    """Disable an alert rule."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        try:
            return await db.update_alert_rule(name, enabled=0)
        finally:
            await db.close()

    updated = asyncio.run(_run())
    if updated:
        typer.echo(f"Alert rule '{name}' disabled.")
    else:
        typer.echo(f"Error: no rule named '{name}' found.", err=True)
        raise typer.Exit(1)


# --- Skill management ---

skills_app = typer.Typer(name="skills", help="Manage skills.")
app.add_typer(skills_app)


@skills_app.command("list")
def skills_list() -> None:
    """List all skills."""
    from .config import SkillsConfig
    from .skills import SkillService

    skills_config = SkillsConfig()
    service = SkillService(skills_config.path)
    skills = service.list_skills()

    if not skills:
        typer.echo("No skills configured.")
        return

    console = Console()
    table = Table(title="Skills")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Host", style="blue")
    table.add_column("Trigger", style="yellow")
    table.add_column("Status", style="green")

    for s in skills:
        status = "enabled" if s.enabled else "disabled"
        table.add_row(
            s.name,
            (s.description or "")[:40],
            s.host,
            s.trigger,
            status,
        )

    console.print(table)


@skills_app.command("show")
def skills_show(
    name: Annotated[str, typer.Argument(help="Name of the skill to show")],
) -> None:
    """Show a skill's SKILL.md content."""
    from .config import SkillsConfig
    from .skills import SkillService

    skills_config = SkillsConfig()
    service = SkillService(skills_config.path)
    skill = service.get_skill(name)

    if not skill:
        typer.echo(f"Error: no skill named '{name}' found.", err=True)
        raise typer.Exit(1)

    console = Console()
    status = "enabled" if skill.enabled else "disabled"
    console.print(f"[bold cyan]{skill.name}[/bold cyan]  [{status}]")
    if skill.description:
        console.print(f"  {skill.description}")
    console.print(f"  Host: {skill.host}  |  Trigger: {skill.trigger}")
    console.print()

    if skill.instructions:
        console.print("[bold]Instructions:[/bold]")
        console.print(f"  {skill.instructions}")
    else:
        console.print("  (no instructions)")


@skills_app.command("add")
def skills_add(
    name: Annotated[str, typer.Option("--name", "-n", help="Skill name (lowercase, hyphens, max 64 chars)")],
    description: Annotated[str, typer.Option("--description", "-d", help="Skill description (required)")],
    instructions_file: Annotated[
        str | None, typer.Option("--instructions-file", "-f", help="Markdown file with skill instructions")
    ] = None,
    host: Annotated[str, typer.Option("--host", help="Target host ('all' or specific name)")] = "all",
    trigger: Annotated[str, typer.Option("--trigger", "-t", help="'manual' or 'watch'")] = "manual",
) -> None:
    """Add a new skill."""
    from pathlib import Path

    from .config import SkillsConfig
    from .skills import Skill, SkillService

    if trigger not in ("manual", "watch"):
        typer.echo("Error: trigger must be 'manual' or 'watch'.", err=True)
        raise typer.Exit(1)

    if not description.strip():
        typer.echo("Error: --description is required.", err=True)
        raise typer.Exit(1)

    instructions = ""
    if instructions_file:
        path = Path(instructions_file)
        if not path.exists():
            typer.echo(f"Error: file not found: {instructions_file}", err=True)
            raise typer.Exit(1)
        instructions = path.read_text().strip()

    if not instructions:
        typer.echo("Error: provide instructions via --instructions-file.", err=True)
        raise typer.Exit(1)

    skills_config = SkillsConfig()
    service = SkillService(skills_config.path)

    if service.get_skill(name):
        typer.echo(f"Error: a skill named '{name}' already exists.", err=True)
        raise typer.Exit(1)

    try:
        skill = Skill(
            name=name,
            description=description,
            host=host,
            trigger=trigger,
            instructions=instructions,
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    service.save_skill(skill)
    typer.echo(f"Skill '{name}' created.")


@skills_app.command("remove")
def skills_remove(
    name: Annotated[str, typer.Argument(help="Name of the skill to remove")],
) -> None:
    """Remove a skill by name."""
    from .config import SkillsConfig
    from .skills import SkillService

    skills_config = SkillsConfig()
    service = SkillService(skills_config.path)
    deleted = service.delete_skill(name)
    if deleted:
        typer.echo(f"Skill '{name}' removed.")
    else:
        typer.echo(f"Error: no skill named '{name}' found.", err=True)
        raise typer.Exit(1)


@skills_app.command("enable")
def skills_enable(
    name: Annotated[str, typer.Argument(help="Name of the skill to enable")],
) -> None:
    """Enable a skill."""
    from .config import SkillsConfig
    from .skills import SkillService

    skills_config = SkillsConfig()
    service = SkillService(skills_config.path)
    skill = service.get_skill(name)
    if not skill:
        typer.echo(f"Error: no skill named '{name}' found.", err=True)
        raise typer.Exit(1)
    updated = skill.model_copy(update={"enabled": True})
    service.save_skill(updated)
    typer.echo(f"Skill '{name}' enabled.")


@skills_app.command("disable")
def skills_disable(
    name: Annotated[str, typer.Argument(help="Name of the skill to disable")],
) -> None:
    """Disable a skill."""
    from .config import SkillsConfig
    from .skills import SkillService

    skills_config = SkillsConfig()
    service = SkillService(skills_config.path)
    skill = service.get_skill(name)
    if not skill:
        typer.echo(f"Error: no skill named '{name}' found.", err=True)
        raise typer.Exit(1)
    updated = skill.model_copy(update={"enabled": False})
    service.save_skill(updated)
    typer.echo(f"Skill '{name}' disabled.")


if __name__ == "__main__":
    app()
