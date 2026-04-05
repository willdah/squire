"""FastAPI application factory for the Squire web interface."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..config import (
    AppConfig,
    DatabaseConfig,
    GuardrailsConfig,
    LLMConfig,
    NotificationsConfig,
    SkillsConfig,
    WatchConfig,
)
from ..database.service import DatabaseService
from ..hosts.store import HostStore
from ..main import _collect_all_snapshots
from ..notifications.webhook import WebhookDispatcher
from ..skills import SkillService
from ..system.registry import BackendRegistry
from ..tools import set_db as tools_set_db
from ..tools import set_notifier as tools_set_notifier
from ..tools import set_registry as tools_set_registry
from . import dependencies as deps
from .routers import alerts, chat, config, events, hosts, sessions, skills, system, watch

load_dotenv()
logger = logging.getLogger(__name__)

# Latest snapshot cache — updated by background task
_latest_snapshot: dict[str, dict] = {}
_snapshot_lock = asyncio.Lock()


async def get_latest_snapshot() -> dict[str, dict]:
    async with _snapshot_lock:
        return dict(_latest_snapshot)


async def set_latest_snapshot(snapshot: dict[str, dict]) -> None:
    async with _snapshot_lock:
        _latest_snapshot.clear()
        _latest_snapshot.update(snapshot)


async def _background_snapshots(db: DatabaseService, interval_minutes: int, registry: BackendRegistry) -> None:
    """Periodically collect and persist system snapshots."""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            snapshot = await _collect_all_snapshots(registry)
            if "local" in snapshot:
                await db.save_snapshot(snapshot["local"])
            await set_latest_snapshot(snapshot)
        except Exception:
            logger.debug("Background snapshot failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize shared services on startup, clean up on shutdown."""
    # Load all configs
    deps.app_config = AppConfig()
    deps.llm_config = LLMConfig()
    deps.db_config = DatabaseConfig()
    deps.notif_config = NotificationsConfig()
    deps.watch_config = WatchConfig()
    deps.guardrails = GuardrailsConfig()
    skills_config = SkillsConfig()

    # Create service singletons
    deps.registry = BackendRegistry()
    deps.db = DatabaseService(deps.db_config.path)
    from ..notifications.email import EmailNotifier
    from ..notifications.router import NotificationRouter

    webhook_dispatcher = WebhookDispatcher(deps.notif_config)
    email_notifier = None
    if deps.notif_config.email and deps.notif_config.email.enabled:
        email_notifier = EmailNotifier(deps.notif_config.email)
    deps.notifier = NotificationRouter(webhook=webhook_dispatcher, email=email_notifier)
    deps.skills_service = SkillService(skills_config.path)

    # Load managed hosts from DB into the registry
    deps.host_store = HostStore(deps.db, deps.registry)
    await deps.host_store.load()

    # Wire up tool registry
    tools_set_registry(deps.registry)
    tools_set_db(deps.db)
    tools_set_notifier(deps.notifier)

    # Collect initial snapshots
    try:
        snapshot = await _collect_all_snapshots(deps.registry)
        if "local" in snapshot:
            await deps.db.save_snapshot(snapshot["local"])
        await set_latest_snapshot(snapshot)
    except Exception:
        logger.warning("Initial snapshot collection failed", exc_info=True)

    # Start background snapshot collection
    snapshot_task = asyncio.create_task(
        _background_snapshots(deps.db, deps.db_config.snapshot_interval_minutes, deps.registry)
    )

    logger.info("Squire web API started")
    yield

    # Shutdown
    snapshot_task.cancel()
    try:
        await snapshot_task
    except asyncio.CancelledError:
        pass
    await deps.registry.close_all()
    await deps.notifier.close()
    await deps.db.close()
    logger.info("Squire web API stopped")


def _find_static_dir() -> Path | None:
    """Locate the Next.js static export directory."""
    # Check relative to the package (installed)
    pkg_dir = Path(__file__).resolve().parent.parent.parent.parent / "web" / "out"
    if pkg_dir.is_dir():
        return pkg_dir
    # Check cwd (development)
    cwd_dir = Path.cwd() / "web" / "out"
    if cwd_dir.is_dir():
        return cwd_dir
    return None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    static_dir = _find_static_dir()

    app = FastAPI(
        title="Squire",
        description="AI-powered homelab management",
        version="0.4.0",
        lifespan=lifespan,
    )

    # CORS for local development (Next.js dev server)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    app.include_router(hosts.router, prefix="/api/hosts", tags=["hosts"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(watch.router, prefix="/api/watch", tags=["watch"])

    if static_dir:
        logger.info("Serving frontend from %s", static_dir)
        # Mount the static export as a catch-all file server.
        # html=True serves index.html for directory paths (e.g., / -> /index.html).
        # This mount goes LAST so API routers take precedence.
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
    else:
        # No frontend build found — show helpful message
        @app.get("/")
        async def serve_no_frontend():
            return HTMLResponse(
                content=(
                    "<html><body style='font-family:system-ui;max-width:600px;margin:80px auto;color:#333'>"
                    "<h1>Squire API</h1>"
                    "<p>The API is running. To use the web interface:</p>"
                    "<ol>"
                    "<li>Build the frontend: <code>cd web && npm install && npm run build</code></li>"
                    "<li>Restart: <code>squire web</code></li>"
                    "</ol>"
                    "<p>Or for development, run <code>cd web && npm run dev</code> separately "
                    "(frontend on port 3000, API on this port).</p>"
                    "<p><a href='/docs'>API Documentation (Swagger)</a></p>"
                    "</body></html>"
                ),
                status_code=200,
            )

    return app
