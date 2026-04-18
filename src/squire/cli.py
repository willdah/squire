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
            ",".join(s.hosts),
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
    console.print(f"  Hosts: {', '.join(skill.hosts)}  |  Trigger: {skill.trigger}")
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
    hosts: Annotated[
        str, typer.Option("--hosts", help="Comma-separated target hosts (use 'all' for unrestricted)")
    ] = "all",
    trigger: Annotated[str, typer.Option("--trigger", "-t", help="'manual' or 'watch'")] = "manual",
) -> None:
    host_list = [h.strip() for h in hosts.split(",") if h.strip()]
    if not host_list:
        host_list = ["all"]

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
            hosts=host_list,
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


# --- Host management ---

hosts_app = typer.Typer(name="hosts", help="Manage remote hosts.")
app.add_typer(hosts_app)


@hosts_app.command("list")
def hosts_list() -> None:
    """List all managed hosts."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            return await store.list_hosts(), await db.list_managed_hosts()
        finally:
            await db.close()

    configs, rows = asyncio.run(_run())

    if not configs:
        typer.echo("No managed hosts. Add one with: squire hosts add")
        return

    status_map = {r["name"]: r["status"] for r in rows}
    console = Console()
    table = Table(title="Managed Hosts")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Address", style="white")
    table.add_column("User", style="blue")
    table.add_column("Port", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Tags", style="yellow")

    for cfg in configs:
        status = status_map.get(cfg.name, "unknown")
        tags = ", ".join(cfg.tags) if cfg.tags else ""
        table.add_row(cfg.name, cfg.address, cfg.user, str(cfg.port), status, tags)

    console.print(table)


@hosts_app.command("add")
def hosts_add(
    name: Annotated[str, typer.Option("--name", "-n", help="Unique host alias")],
    address: Annotated[str, typer.Option("--address", "-a", help="Hostname or IP address")],
    user: Annotated[str, typer.Option("--user", "-u", help="SSH username")] = "root",
    port: Annotated[int, typer.Option("--port", "-p", help="SSH port")] = 22,
    tags: Annotated[str | None, typer.Option("--tags", "-t", help="Comma-separated tags")] = None,
    services: Annotated[str | None, typer.Option("--services", "-s", help="Comma-separated service names")] = None,
    service_root: Annotated[str, typer.Option("--service-root", help="Root directory for compose services")] = "/opt",
) -> None:
    """Enroll a new remote host."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    svc_list = [s.strip() for s in services.split(",") if s.strip()] if services else []

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            return await store.enroll(
                name=name,
                address=address,
                user=user,
                port=port,
                tags=tag_list,
                services=svc_list,
                service_root=service_root,
            )
        finally:
            await db.close()

    try:
        result = asyncio.run(_run())
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Generated SSH key for '{name}'.")
    if result.status == "active":
        typer.echo(result.message)
        typer.echo(f"Host '{name}' enrolled successfully.")
    else:
        typer.echo(result.message)
        typer.echo()
        typer.echo("Add this public key to ~/.ssh/authorized_keys on the remote host:")
        typer.echo()
        typer.echo(f"  {result.public_key}")
        typer.echo()
        typer.echo(f"Then run: squire hosts verify {name}")


@hosts_app.command("verify")
def hosts_verify(
    name: Annotated[str, typer.Argument(help="Name of the host to verify")],
) -> None:
    """Verify connectivity to a managed host."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            await store.load()
            return await store.verify(name)
        finally:
            await db.close()

    try:
        reachable = asyncio.run(_run())
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if reachable:
        typer.echo(f"Host '{name}' is reachable. Status updated to active.")
    else:
        typer.echo(f"Could not connect to '{name}'. Check that the public key is installed.")
        raise typer.Exit(1)


@hosts_app.command("remove")
def hosts_remove(
    name: Annotated[str, typer.Argument(help="Name of the host to remove")],
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Remove a managed host."""
    from .config import DatabaseConfig
    from .database.service import DatabaseService
    from .hosts.store import HostStore
    from .system.registry import BackendRegistry

    if not yes and not typer.confirm(f"Remove host '{name}'? This deletes the SSH key."):
        raise typer.Abort()

    async def _run():
        db_config = DatabaseConfig()
        db = DatabaseService(db_config.path)
        registry = BackendRegistry()
        store = HostStore(db, registry)
        try:
            await store.load()
            await store.remove(name)
        finally:
            await db.close()

    try:
        asyncio.run(_run())
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Host '{name}' removed.")


if __name__ == "__main__":
    app()
