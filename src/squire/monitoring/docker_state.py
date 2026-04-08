"""Docker container state inspection for monitor loops."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from ..system.registry import BackendRegistry

logger = logging.getLogger(__name__)

Outcome = Literal["met", "failed", "pending"]


async def fetch_container_state_json(registry: BackendRegistry, host: str, container: str) -> dict[str, Any] | None:
    """Return Docker ``.State`` object as dict, or None if inspect failed."""
    backend = registry.get(host)
    result = await backend.run(
        ["docker", "inspect", "--format", "{{json .State}}", container],
        timeout=30.0,
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip() or "unknown error"
        logger.debug("docker inspect failed for %s on %s: %s", container, host, err)
        return None
    raw = (result.stdout or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Invalid docker inspect JSON for %s", container, exc_info=True)
        return None


def evaluate_container_condition(state: dict[str, Any], condition: str) -> tuple[Outcome, str]:
    """Classify whether ``condition`` is satisfied given Docker ``State`` JSON.

    Returns:
        (outcome, human-readable detail). ``met`` means stop successfully;
        ``failed`` means abort; ``pending`` means keep polling.
    """
    condition = condition.strip().lower()
    running = bool(state.get("Running"))
    status = str(state.get("Status", ""))
    exit_code = state.get("ExitCode")
    health = state.get("Health")

    if condition == "running":
        if running:
            return "met", "Container is running."
        if "dead" in status.lower():
            return "failed", f"Container is dead (status: {status})."
        if exit_code not in (None, 0) and not running:
            return "failed", f"Container stopped with exit code {exit_code}."
        return "pending", f"Not running yet (status: {status})."

    if condition == "healthy":
        if not health:
            return "failed", "Container has no health check configured; cannot wait for healthy."
        hs = str(health.get("Status", "")).lower()
        if hs == "healthy":
            return "met", "Health check reports healthy."
        if hs == "unhealthy":
            return "failed", "Health check reports unhealthy."
        return "pending", f"Health status: {health.get('Status', hs)}."

    if condition == "exited":
        if not running:
            return "met", "Container is stopped."
        return "pending", "Container still running."

    return "failed", f"Unknown condition '{condition}'. Use: running, healthy, or exited."
