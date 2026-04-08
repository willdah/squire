"""wait_for_state — poll until a Docker container reaches a target condition."""

from __future__ import annotations

import asyncio
import logging
import uuid

from google.adk.tools.tool_context import ToolContext

from ..monitoring.loop import run_docker_container_monitor
from ..monitoring.registry import track_monitor_task
from ..monitoring.sinks import get_monitor_session_sink
from ._registry import get_registry

logger = logging.getLogger(__name__)

RISK_LEVEL = 1  # read-only polling

_MAX_TIMEOUT = 3600
_MAX_INTERVAL = 120
_KIND_DOCKER_CONTAINER = "docker_container"


async def wait_for_state(
    kind: str,
    container: str,
    condition: str,
    host: str = "local",
    interval_seconds: int = 5,
    timeout_seconds: int = 120,
    tool_context: ToolContext | None = None,
) -> str:
    """Poll infrastructure state until a condition is met, without LLM calls each tick.

    Use after a state-changing action when the user asked to wait for a stable state
    (e.g. restart + "make sure it's healthy").

    Args:
        kind: What to watch. Supported: ``docker_container``.
        container: Docker container name or ID.
        condition: Target state: ``healthy`` (requires a health check), ``running``, or ``exited``.
        host: Target host (default ``local``).
        interval_seconds: Seconds between checks (default 5, max 120).
        timeout_seconds: Max wait in seconds (default 120, max 3600).
        tool_context: Injected by ADK (session id for background delivery).

    Returns:
        Immediate acknowledgment when monitoring runs in the background; otherwise
        the final result string after polling completes.
    """
    kind_norm = (kind or "").strip().lower()
    if kind_norm != _KIND_DOCKER_CONTAINER:
        return f"Unsupported kind '{kind}'. Use '{_KIND_DOCKER_CONTAINER}'."

    if not container.strip():
        return "Error: container name is required."

    cond = (condition or "").strip().lower()
    if cond not in ("healthy", "running", "exited"):
        return "Invalid condition. Use: healthy, running, or exited."

    interval = max(1, min(int(interval_seconds), _MAX_INTERVAL))
    timeout = max(1, min(int(timeout_seconds), _MAX_TIMEOUT))

    registry = get_registry()
    resolved_host = host
    if host == "local":
        matched = registry.resolve_host_for_service(container)
        if matched:
            resolved_host = matched

    session_id = tool_context.session.id if tool_context else ""
    sink = get_monitor_session_sink(session_id) if session_id else None
    use_background = bool(sink and getattr(sink, "use_background", False))

    monitor_id = str(uuid.uuid4())[:8]

    async def _run() -> None:
        assert sink is not None
        try:
            result = await run_docker_container_monitor(
                registry=registry,
                host=resolved_host,
                container=container.strip(),
                condition=cond,
                interval_seconds=interval,
                timeout_seconds=timeout,
                on_progress=None,
            )
            if result.status == "success":
                body = result.message
            else:
                body = f"[Monitor {monitor_id}] {result.message}"

            await sink.deliver_monitor_result(monitor_id, body)
        except asyncio.CancelledError:
            raise

    if use_background:
        task = asyncio.create_task(_run())
        track_monitor_task(session_id, task)
        return (
            f"Monitor {monitor_id} started: waiting for container '{container}' on host '{resolved_host}' "
            f"to be '{cond}' (every {interval}s, timeout {timeout}s). "
            "You will get another message when it finishes."
        )

    async def _progress(line: str) -> None:
        print(line, flush=True)

    try:
        result = await run_docker_container_monitor(
            registry=registry,
            host=resolved_host,
            container=container.strip(),
            condition=cond,
            interval_seconds=interval,
            timeout_seconds=timeout,
            on_progress=_progress,
        )
    except Exception as exc:
        logger.exception("wait_for_state failed")
        return f"Error while monitoring: {exc}"

    return result.message
