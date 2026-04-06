"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health():
    """Lightweight liveness check — confirms the web server is responsive."""
    return {"status": "ok"}
