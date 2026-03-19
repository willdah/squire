"""Watch mode status endpoint."""

from fastapi import APIRouter, Depends

from ..dependencies import get_db
from ..schemas import WatchStatusResponse

router = APIRouter()


@router.get("/status", response_model=WatchStatusResponse)
async def watch_status(db=Depends(get_db)):
    """Current watch mode state."""
    state = await db.get_all_watch_state()
    if not state:
        return WatchStatusResponse()
    return WatchStatusResponse(**state)
