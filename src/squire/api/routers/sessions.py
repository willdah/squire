"""Session history endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_db
from ..schemas import MessageInfo, SessionInfo

router = APIRouter()


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


@router.delete("/{session_id}")
async def delete_session(session_id: str, db=Depends(get_db)):
    """Delete a session and its messages."""
    conn = await db._get_conn()
    await conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    cursor = await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    await conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"deleted": True}
