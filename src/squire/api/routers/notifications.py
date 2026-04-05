"""Notification management endpoints."""

from fastapi import APIRouter, HTTPException

from .. import dependencies as deps

router = APIRouter()


@router.post("/test-email")
async def test_email():
    """Send a test email using the current email configuration."""
    notifier = deps.get_notifier()
    email = getattr(notifier, "_email", None)
    if email is None:
        raise HTTPException(status_code=400, detail="Email notifications are not configured")

    try:
        await email.dispatch(
            category="test",
            summary="Test email from Squire",
            details="If you received this, email notifications are working correctly.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {e}")

    return {"status": "ok", "message": "Test email sent"}
