"""Shared helpers for snapshots and session listing (web API, watch mode, CLI)."""

import asyncio
import json
import logging

from dotenv import load_dotenv

from .config import DatabaseConfig
from .database.service import DatabaseService
from .system.registry import BackendRegistry
from .tools.docker_ps import docker_ps
from .tools.system_info import system_info

load_dotenv()


async def _collect_snapshot(host: str = "local") -> dict:
    """Run system_info and docker_ps to build a snapshot for a single host.

    Args:
        host: Target host name (default "local").

    Returns a dict suitable for the system prompt and status displays.
    """
    snapshot = {}

    try:
        sys_raw = await system_info(host=host)
        sys_data = json.loads(sys_raw)
        snapshot["hostname"] = sys_data.get("hostname", "unknown")
        snapshot["os_info"] = sys_data.get("os", "")
        snapshot["cpu_percent"] = sys_data.get("cpu_percent", 0)
        snapshot["memory_total_mb"] = sys_data.get("memory_total_mb", 0)
        snapshot["memory_used_mb"] = sys_data.get("memory_used_mb", 0)
        snapshot["uptime"] = sys_data.get("uptime", "")
        snapshot["disk_usage_raw"] = sys_data.get("disk_usage", "")
    except Exception:
        logging.getLogger(__name__).debug("Failed to collect system_info for %s", host, exc_info=True)
        snapshot["hostname"] = host if host != "local" else "unknown"

    try:
        containers_raw = await docker_ps(all_containers=True, format="json", host=host)
        containers = []
        for line in containers_raw.strip().split("\n"):
            line = line.strip()
            if line and line.startswith("{"):
                try:
                    c = json.loads(line)
                    containers.append(
                        {
                            "name": c.get("Names", ""),
                            "image": c.get("Image", ""),
                            "status": c.get("Status", ""),
                            "state": c.get("State", ""),
                            "ports": c.get("Ports", ""),
                        }
                    )
                except json.JSONDecodeError:
                    pass
        snapshot["containers"] = containers
    except Exception:
        logging.getLogger(__name__).debug("Failed to collect docker_ps for %s", host, exc_info=True)
        snapshot["containers"] = []

    return snapshot


async def _collect_all_snapshots(registry: BackendRegistry) -> dict[str, dict]:
    """Collect snapshots from all configured hosts in parallel.

    Returns a dict keyed by host name, where each value is a snapshot dict.
    Unreachable hosts get an error entry instead of raising.
    """

    async def _collect_one(host: str) -> tuple[str, dict]:
        try:
            return (host, await _collect_snapshot(host=host))
        except Exception:
            logging.getLogger(__name__).debug("Failed to collect snapshot for %s", host, exc_info=True)
            return (host, {"hostname": host, "error": "unreachable", "containers": []})

    tasks = [_collect_one(h) for h in registry.host_names]
    results = await asyncio.gather(*tasks)
    return dict(results)


async def list_sessions() -> list[dict]:
    """List recent chat sessions from the database."""
    db_config = DatabaseConfig()
    db = DatabaseService(db_config.path)
    try:
        return await db.list_sessions()
    finally:
        await db.close()
