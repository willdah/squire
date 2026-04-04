"""Watch mode API endpoints — control, status, and history."""

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_db, get_guardrails, get_watch_config
from ..schemas import (
    WatchApprovalAction,
    WatchCommandResponse,
    WatchConfigResponse,
    WatchConfigUpdate,
    WatchStatusResponse,
)

router = APIRouter()


@router.get("/status", response_model=WatchStatusResponse)
async def watch_status(db=Depends(get_db)):
    """Current watch mode state."""
    state = await db.get_all_watch_state()
    if not state:
        return WatchStatusResponse()
    return WatchStatusResponse(**state)


@router.post("/start", response_model=WatchCommandResponse)
async def watch_start(db=Depends(get_db)):
    """Start watch mode if not already running."""
    state = await db.get_all_watch_state()
    pid = state.get("pid")
    if pid and state.get("status") == "running":
        try:
            os.kill(int(pid), 0)
            return WatchCommandResponse(status="ok", message="Watch already running")
        except (ProcessLookupError, ValueError):
            pass

    await db.insert_watch_command("start")

    import subprocess
    import sys

    subprocess.Popen(
        [sys.executable, "-m", "squire", "watch"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return WatchCommandResponse(status="ok", message="Watch starting")


@router.post("/stop", response_model=WatchCommandResponse)
async def watch_stop(db=Depends(get_db)):
    """Stop watch mode."""
    await db.insert_watch_command("stop")
    return WatchCommandResponse(status="ok", message="Stop command sent")


@router.get("/config", response_model=WatchConfigResponse)
async def watch_config_get(
    watch_config=Depends(get_watch_config),
    guardrails=Depends(get_guardrails),
):
    """Get current watch configuration."""
    return WatchConfigResponse(
        interval_minutes=watch_config.interval_minutes,
        cycle_timeout_seconds=watch_config.cycle_timeout_seconds,
        checkin_prompt=watch_config.checkin_prompt,
        notify_on_action=watch_config.notify_on_action,
        notify_on_blocked=watch_config.notify_on_blocked,
        cycles_per_session=watch_config.cycles_per_session,
        risk_tolerance=guardrails.watch_tolerance,
    )


@router.put("/config", response_model=WatchCommandResponse)
async def watch_config_update(update: WatchConfigUpdate, db=Depends(get_db)):
    """Send config update to the running watch process."""
    payload = update.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.insert_watch_command("update_config", payload=json.dumps(payload))
    return WatchCommandResponse(status="ok", message="Config update sent")


@router.get("/cycles")
async def watch_cycles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
) -> list[dict]:
    """Paginated list of watch cycles."""
    return await db.get_watch_cycles(page=page, per_page=per_page)


@router.get("/cycles/{cycle}")
async def watch_cycle_detail(cycle: int, db=Depends(get_db)) -> list[dict]:
    """Full event stream for a specific cycle."""
    return await db.get_watch_events_for_cycle(cycle)


@router.post("/approve/{request_id}", response_model=WatchCommandResponse)
async def watch_approve(
    request_id: str,
    action: WatchApprovalAction,
    db=Depends(get_db),
):
    """Approve or deny a watch mode tool approval request."""
    approval = await db.get_watch_approval(request_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Already resolved: {approval['status']}")

    status = "approved" if action.approved else "denied"
    await db.update_watch_approval(request_id, status)
    return WatchCommandResponse(status="ok", message=f"Tool {status}")
