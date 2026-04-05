"""Send an ad-hoc notification via configured webhooks."""

RISK_LEVEL = 2


async def send_notification(message: str, category: str = "user") -> str:
    """Send a notification message to all configured webhook endpoints.

    Args:
        message: The notification message to send.
        category: Event category for webhook filtering (default: "user").

    Returns:
        Confirmation message or error description.
    """
    from .._registry import get_notifier

    notifier = get_notifier()
    if notifier is None:
        return "Error: notification system not configured."

    try:
        await notifier.dispatch(category=category, summary=message)
        return f"Notification sent: {message}"
    except (OSError, ValueError) as e:
        return f"Error sending notification: {e}"
