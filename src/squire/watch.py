"""Standalone CLI entrypoint for autonomous watch mode.

Historically this module hosted the whole watch subprocess. The real loop
now lives in :mod:`squire.watch_controller` as an in-process
``WatchController`` owned by the FastAPI lifespan. This module is kept as
a thin wrapper so ``squire watch`` still runs headlessly (no web server
required) for air-gapped / CLI-only deployments.
"""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from .config import DatabaseConfig
from .database.service import DatabaseService
from .system.registry import BackendRegistry
from .tools import set_db, set_notifier, set_registry
from .watch_controller import WatchController, build_controller_from_env, run_controller_until_done
from .watch_loop import configure_logging

load_dotenv()

logger = logging.getLogger(__name__)


async def _run_standalone() -> None:
    """Build singletons, run the controller to completion, and clean up."""
    configure_logging()

    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)
    registry = BackendRegistry()
    set_db(db)
    set_registry(registry)

    controller: WatchController | None = None
    try:
        controller = await build_controller_from_env(db, registry)
        set_notifier(controller._notifier)
        await db.finalize_stale_watch_runs_on_boot()
        await run_controller_until_done(controller)
    finally:
        try:
            await registry.close_all()
        except Exception:
            logger.exception("Failed to close backend registry during watch shutdown")
        if controller is not None:
            try:
                await controller._notifier.close()
            except Exception:
                logger.exception("Failed to close notifier during watch shutdown")
        await db.close()


def run_watch() -> None:
    """Synchronous wrapper — the ``squire watch`` CLI entrypoint."""
    asyncio.run(_run_standalone())


async def get_watch_status() -> dict[str, str] | None:
    """Read the current watch state from the database.

    Returns the watch state dict, or None if watch has never run.
    """
    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)
    try:
        state = await db.get_all_watch_state()
        return state if state else None
    finally:
        await db.close()
