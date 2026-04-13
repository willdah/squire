"""Session history endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_adk_runtime, get_app_config, get_db
from ..schemas import MessageInfo, SessionInfo

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=list[SessionInfo])
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """List recent chat sessions."""
    rows = await db.list_sessions(limit=limit)
    return [SessionInfo(**r) for r in rows]


@router.get("/{session_id}/messages", response_model=list[MessageInfo])
async def get_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    db=Depends(get_db),
):
    """Get messages for a session."""
    rows = await db.get_messages(session_id, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found or has no messages")
    return [MessageInfo(**r) for r in rows]


@router.delete("")
async def delete_all_sessions(
    db=Depends(get_db),
    app_config=Depends(get_app_config),
    adk_runtime=Depends(get_adk_runtime),
):
    """Delete all sessions, messages, and durable ADK session state."""
    rows = await db.list_sessions(limit=10_000)
    session_ids = [str(row.get("session_id")) for row in rows if row.get("session_id")]
    count = await db.delete_all_sessions()
    for session_id in session_ids:
        try:
            await adk_runtime.session_service.delete_session(
                app_name=app_config.app_name,
                user_id=app_config.user_id,
                session_id=session_id,
            )
        except Exception:
            logger.debug("Failed to delete ADK session %s during clear", session_id, exc_info=True)
    return {"deleted": count}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db=Depends(get_db),
    app_config=Depends(get_app_config),
    adk_runtime=Depends(get_adk_runtime),
):
    """Delete a session, its messages, and durable ADK session state."""
    deleted = await db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    try:
        await adk_runtime.session_service.delete_session(
            app_name=app_config.app_name,
            user_id=app_config.user_id,
            session_id=session_id,
        )
    except Exception:
        logger.debug("Failed to delete ADK session %s", session_id, exc_info=True)
    return {"deleted": True}
