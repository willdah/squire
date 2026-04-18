"""Watch mode API endpoints — control, status, and history."""

import asyncio

from agent_risk_engine import RuleGate
from fastapi import APIRouter, Body, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..dependencies import get_db, get_guardrails, get_watch_config, get_watch_controller
from ..schemas import (
    WatchApprovalAction,
    WatchAutostartRequest,
    WatchCommandResponse,
    WatchConfigResponse,
    WatchCycleSummary,
    WatchReportInfo,
    WatchRunSummary,
    WatchSessionSummary,
    WatchStatusResponse,
    WatchTimelineItem,
)

router = APIRouter()


def _effective_watch_risk_level(guardrails) -> int:
    """Numeric risk threshold (1–5) used in watch mode UI and live updates."""
    wt = guardrails.watch_tolerance or guardrails.risk_tolerance
    return RuleGate(threshold=wt, strict=True, allowed=set(), denied=set()).threshold


async def _increment_supervisor_count(db) -> None:
    """Increment supervisor connection count."""
    current = await db.get_watch_state("supervisor_count")
    count = int(current or "0") + 1
    await db.set_watch_state("supervisor_count", str(count))
    await db.set_watch_state("supervisor_connected", "true")


async def _decrement_supervisor_count(db) -> None:
    """Decrement supervisor connection count."""
    current = await db.get_watch_state("supervisor_count")
    count = max(0, int(current or "0") - 1)
    await db.set_watch_state("supervisor_count", str(count))
    await db.set_watch_state("supervisor_connected", str(count > 0).lower())


@router.get("/status", response_model=WatchStatusResponse)
async def watch_status(db=Depends(get_db), controller=Depends(get_watch_controller)):
    """Current watch mode state.

    Merges the in-memory controller state (authoritative for running/failed)
    with DB-persisted counters and timestamps.
    """
    state = await db.get_all_watch_state()
    runtime = controller.status()
    payload = dict(state or {})
    payload["state"] = runtime.state
    if runtime.last_error:
        payload["last_error"] = runtime.last_error
    # Keep the legacy ``status`` field aligned for older clients.
    if runtime.state == "running":
        payload["status"] = "running"
    elif runtime.state == "failed":
        payload["status"] = "failed"
    else:
        payload.setdefault("status", "stopped")
    return WatchStatusResponse(**payload)


@router.post("/start", response_model=WatchCommandResponse)
async def watch_start(controller=Depends(get_watch_controller)):
    """Start watch mode if not already running."""
    result = await controller.start()
    return WatchCommandResponse(status=result.status, message=result.message)


@router.post("/stop", response_model=WatchCommandResponse)
async def watch_stop(controller=Depends(get_watch_controller)):
    """Stop watch mode. Graceful; cancels after 30s if a cycle is still running."""
    await controller.stop()
    return WatchCommandResponse(status="ok", message="Watch stop requested")


@router.post("/autostart", response_model=WatchCommandResponse)
async def watch_autostart(body: WatchAutostartRequest = Body(...), db=Depends(get_db)):
    """Persist the user's auto-start-on-boot intent.

    When ``enabled`` is true, the FastAPI lifespan calls ``controller.start()``
    after the container boots so watch survives restarts without a manual click.
    """
    await db.set_watch_state("watch_autostart", "true" if body.enabled else "false")
    return WatchCommandResponse(
        status="ok",
        message=("Auto-start enabled" if body.enabled else "Auto-start disabled"),
    )


@router.get("/config", response_model=WatchConfigResponse)
async def watch_config_get(
    watch_config=Depends(get_watch_config),
    guardrails=Depends(get_guardrails),
):
    """Get current watch configuration."""
    return WatchConfigResponse(
        interval_minutes=watch_config.interval_minutes,
        max_tool_calls_per_cycle=watch_config.max_tool_calls_per_cycle,
        cycle_timeout_seconds=watch_config.cycle_timeout_seconds,
        checkin_prompt=watch_config.checkin_prompt,
        notify_on_action=watch_config.notify_on_action,
        notify_on_blocked=watch_config.notify_on_blocked,
        cycles_per_session=watch_config.cycles_per_session,
        max_context_events=watch_config.max_context_events,
        max_identical_actions_per_cycle=watch_config.max_identical_actions_per_cycle,
        blocked_action_cooldown_cycles=watch_config.blocked_action_cooldown_cycles,
        max_remote_actions_per_cycle=watch_config.max_remote_actions_per_cycle,
        risk_tolerance=_effective_watch_risk_level(guardrails),
    )


@router.get("/cycles")
async def watch_cycles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    watch_id: str | None = Query(None),
    watch_session_id: str | None = Query(None),
    db=Depends(get_db),
) -> list[dict]:
    """Paginated list of watch cycles."""
    if not isinstance(watch_id, str):
        watch_id = None
    if not isinstance(watch_session_id, str):
        watch_session_id = None
    return await db.get_watch_cycles(
        page=page,
        per_page=per_page,
        watch_id=watch_id,
        watch_session_id=watch_session_id,
    )


@router.delete(
    "/cycles",
    response_model=WatchCommandResponse,
    summary="Delete all persisted watch datastore rows",
    description=(
        "Removes every row from watch_reports, watch_sessions, watch_cycles, watch_runs, and "
        "watch_events. Activity feed rows in the events table (chat, notifications, etc.) are not deleted."
    ),
)
async def watch_delete_cycles(db=Depends(get_db)) -> WatchCommandResponse:
    """Delete the full watch history tables (not only cycle rows).

    Path remains ``/cycles`` for API compatibility; clients should treat this as a watch datastore reset.
    """
    await db.delete_watch_cycles()
    return WatchCommandResponse(
        status="ok",
        message="Watch datastore cleared (runs, sessions, cycles, reports, watch events)",
    )


@router.get("/cycles/{cycle_id}")
async def watch_cycle_detail(cycle_id: str, watch_id: str | None = Query(None), db=Depends(get_db)) -> list[dict]:
    """Full event stream for a specific cycle."""
    if not isinstance(watch_id, str):
        watch_id = None
    if cycle_id.isdigit():
        return await db.get_watch_events_for_cycle(int(cycle_id), watch_id=watch_id)
    return await db.get_watch_events_for_cycle(cycle_id, watch_id=watch_id)


@router.get("/reports", response_model=list[WatchReportInfo])
async def watch_reports(
    watch_id: str | None = Query(None, description="When set, restrict to this watch run"),
    watch_session_id: str | None = Query(None, description="When set, restrict to this watch session"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """List watch/session completion reports (paginated)."""
    rows = await db.list_watch_reports(
        watch_id=watch_id,
        watch_session_id=watch_session_id,
        page=page,
        per_page=per_page,
    )
    return [WatchReportInfo(**row) for row in rows]


@router.get("/reports/{report_id}", response_model=WatchReportInfo)
async def watch_report_detail(report_id: str, db=Depends(get_db)):
    """Fetch a report by report identifier."""
    row = await db.get_watch_report(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return WatchReportInfo(**row)


@router.get("/reports/watch/{watch_id}", response_model=WatchReportInfo)
async def watch_completion_report(watch_id: str, db=Depends(get_db)):
    """Latest watch-completion report for a watch run."""
    row = await db.get_watch_completion_report(watch_id)
    if not row:
        raise HTTPException(status_code=404, detail="Watch report not found")
    return WatchReportInfo(**row)


@router.get("/reports/session/{watch_session_id}", response_model=WatchReportInfo)
async def watch_session_report(
    watch_session_id: str,
    watch_id: str = Query(..., description="Required; session reports are scoped to a watch run"),
    db=Depends(get_db),
):
    """Latest session report for a watch session within the given watch run."""
    row = await db.get_watch_session_report(watch_id, watch_session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session report not found")
    return WatchReportInfo(**row)


@router.get("/timeline", response_model=list[WatchTimelineItem])
async def watch_timeline(
    watch_id: str | None = Query(None),
    watch_session_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=200),
    db=Depends(get_db),
):
    """Watch-scoped timeline for Watch Explorer / investigation UI.

    ``GET /api/events/timeline`` returns the same rows for Activity and cross-surface deep links;
    prefer this route when building watch-only clients.
    """
    rows = await db.get_watch_activity_timeline(
        watch_id=watch_id,
        watch_session_id=watch_session_id,
        page=page,
        per_page=per_page,
    )
    return [WatchTimelineItem(**row) for row in rows]


@router.get("/runs", response_model=list[WatchRunSummary])
async def watch_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    db=Depends(get_db),
):
    """List watch runs for hierarchy-first reports navigation."""
    rows = await db.list_watch_runs(page=page, per_page=per_page)
    return [WatchRunSummary(**row) for row in rows]


@router.get("/runs/{watch_id}", response_model=WatchRunSummary)
async def watch_run_detail(watch_id: str, db=Depends(get_db)):
    """Fetch one watch run summary."""
    row = await db.get_watch_run(watch_id)
    if not row:
        raise HTTPException(status_code=404, detail="Watch run not found")
    return WatchRunSummary(**row)


@router.get("/runs/{watch_id}/sessions", response_model=list[WatchSessionSummary])
async def watch_run_sessions(
    watch_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=300),
    db=Depends(get_db),
):
    """List sessions for a watch run."""
    rows = await db.list_watch_sessions_for_run(watch_id, page=page, per_page=per_page)
    return [WatchSessionSummary(**row) for row in rows]


@router.get("/runs/{watch_id}/sessions/{watch_session_id}/cycles", response_model=list[WatchCycleSummary])
async def watch_run_session_cycles(
    watch_id: str,
    watch_session_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db=Depends(get_db),
):
    """List cycles under a watch session."""
    rows = await db.list_watch_cycles_for_session(
        watch_id,
        watch_session_id,
        page=page,
        per_page=per_page,
    )
    return [WatchCycleSummary(**row) for row in rows]


@router.get("/sessions/by-adk/{adk_session_id}", response_model=WatchSessionSummary)
async def watch_session_by_adk_session_id(adk_session_id: str, db=Depends(get_db)):
    """Resolve a watch session by ADK session id (chat session id)."""
    row = await db.get_watch_session_by_adk_session_id(adk_session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Watch session not found for adk_session_id")
    return WatchSessionSummary(**row)


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


@router.websocket("/ws")
async def watch_ws(websocket: WebSocket, db=Depends(get_db)):
    """Live watch event stream via WebSocket."""
    await websocket.accept()
    await _increment_supervisor_count(db)

    try:
        # Send initial burst of current cycle events
        state = await db.get_all_watch_state()
        current_cycle = int(state.get("cycle", "0"))
        current_cycle_id = state.get("cycle_id")
        current_watch_id = state.get("watch_id")
        if current_cycle_id:
            events = await db.get_watch_events_for_cycle(current_cycle_id, watch_id=current_watch_id)
            for event in events:
                await websocket.send_json(event)
            last_id = events[-1]["id"] if events else 0
        elif current_cycle > 0:
            events = await db.get_watch_events_for_cycle(current_cycle, watch_id=current_watch_id)
            for event in events:
                await websocket.send_json(event)
            last_id = events[-1]["id"] if events else 0
        else:
            last_id = 0

        # Tail loop — poll for new events every 200ms
        while True:
            new_events = await db.get_watch_events_since(last_id, limit=100, watch_id=current_watch_id)
            for event in new_events:
                await websocket.send_json(event)
                last_id = event["id"]

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.2)
            except TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        await _decrement_supervisor_count(db)
