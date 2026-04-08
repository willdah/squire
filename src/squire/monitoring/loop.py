"""Async poll loop until condition, timeout, or failure."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from ..system.registry import BackendRegistry
from .docker_state import evaluate_container_condition, fetch_container_state_json

ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass
class MonitorLoopResult:
    """Outcome of a monitor loop."""

    status: Literal["success", "timeout", "error"]
    message: str
    elapsed_seconds: float
    last_detail: str = ""


async def run_docker_container_monitor(
    *,
    registry: BackendRegistry,
    host: str,
    container: str,
    condition: str,
    interval_seconds: int,
    timeout_seconds: int,
    initial_delay_seconds: float = 0,
    on_progress: ProgressCallback | None = None,
) -> MonitorLoopResult:
    """Poll ``docker inspect`` until ``evaluate_container_condition`` reports met/failed or time runs out.

    Args:
        initial_delay_seconds: Sleep this long before the first poll.
            Useful after a state-changing action (e.g. ``docker restart``)
            so Docker has time to reset health status.
    """
    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    deadline = time.monotonic() + timeout_seconds
    last_detail = ""
    cond = condition.strip().lower()

    while time.monotonic() < deadline:
        state = await fetch_container_state_json(registry, host, container)
        if state is None:
            return MonitorLoopResult(
                status="error",
                message=f"Could not inspect container '{container}' on host '{host}' (missing or docker error).",
                elapsed_seconds=timeout_seconds - max(0.0, deadline - time.monotonic()),
                last_detail=last_detail,
            )

        outcome, detail = evaluate_container_condition(state, cond)
        last_detail = detail
        elapsed = timeout_seconds - max(0.0, deadline - time.monotonic())

        if outcome == "met":
            return MonitorLoopResult(
                status="success",
                message=f"✓ {container} on {host}: {detail} (after {elapsed:.0f}s).",
                elapsed_seconds=elapsed,
                last_detail=detail,
            )
        if outcome == "failed":
            return MonitorLoopResult(
                status="error",
                message=f"✗ {container} on {host}: {detail}",
                elapsed_seconds=elapsed,
                last_detail=detail,
            )

        if on_progress:
            await on_progress(f"⏳ {detail} ({elapsed:.0f}s / {timeout_seconds}s)")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(float(interval_seconds), max(remaining, 0.01)))

    elapsed = timeout_seconds
    return MonitorLoopResult(
        status="timeout",
        message=(
            f"Timed out after {timeout_seconds}s waiting for '{container}' on '{host}' "
            f"to reach '{cond}'. Last state: {last_detail}"
        ),
        elapsed_seconds=float(timeout_seconds),
        last_detail=last_detail,
    )
