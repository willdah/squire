"""Delete an existing alert rule."""

RISK_LEVEL = 3


async def delete_alert_rule(name: str) -> str:
    """Delete an alert rule by name.

    Args:
        name: The name of the alert rule to delete.

    Returns:
        Confirmation message or error description.
    """
    from .._registry import get_db

    db = get_db()
    if db is None:
        return "Error: database not configured."

    deleted = await db.delete_alert_rule(name)
    if deleted:
        return f"Alert rule '{name}' deleted."
    return f"Error: no alert rule named '{name}' found."
