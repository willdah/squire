"""Update an existing alert rule."""

RISK_LEVEL = 2


async def update_alert_rule(
    name: str,
    condition: str | None = None,
    host: str | None = None,
    severity: str | None = None,
    cooldown_minutes: int | None = None,
    enabled: bool | None = None,
) -> str:
    """Update fields on an existing alert rule.

    Args:
        name: Name of the alert rule to update.
        condition: New condition expression (e.g. "cpu_percent > 90").
        host: Target host name or "all".
        severity: Alert severity — "info", "warning", or "critical".
        cooldown_minutes: Minutes before the alert can fire again.
        enabled: Whether the rule is active.

    Returns:
        Confirmation message with updated rule details.
    """
    from ...notifications.conditions import ConditionError, parse_condition
    from .._registry import get_db

    fields: dict = {}
    if condition is not None:
        try:
            parse_condition(condition)
        except ConditionError as e:
            return f"Error: invalid condition: {e}"
        fields["condition"] = condition
    if host is not None:
        fields["host"] = host
    if severity is not None:
        if severity not in ("info", "warning", "critical"):
            return "Error: severity must be 'info', 'warning', or 'critical'"
        fields["severity"] = severity
    if cooldown_minutes is not None:
        fields["cooldown_minutes"] = cooldown_minutes
    if enabled is not None:
        fields["enabled"] = enabled

    if not fields:
        return "Error: no fields to update"

    db = get_db()
    if db is None:
        return "Error: database not configured."

    updated = await db.update_alert_rule(name, **fields)
    if not updated:
        return f"Error: alert rule '{name}' not found"

    return f"Updated alert rule '{name}': {', '.join(f'{k}={v}' for k, v in fields.items())}"
