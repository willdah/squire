"""Update an existing alert rule."""

from typing import Literal

RISK_LEVEL = 2

AlertField = Literal["cpu_percent", "memory_used_mb", "memory_total_mb", "disk_percent"]
AlertOp = Literal[">", "<", ">=", "<=", "==", "!="]
AlertSeverity = Literal["info", "warning", "critical"]


async def update_alert_rule(
    name: str,
    field: AlertField | None = None,
    op: AlertOp | None = None,
    value: float | None = None,
    host: str | None = None,
    severity: AlertSeverity | None = None,
    cooldown_minutes: int | None = None,
    enabled: bool | None = None,
) -> str:
    """Update fields on an existing alert rule.

    To change the condition, pass ``field``, ``op``, and ``value`` together —
    individually they are ignored. Omit all three to keep the current condition.

    Args:
        name: Name of the alert rule to update.
        field: New condition field (cpu_percent, memory_used_mb, memory_total_mb, disk_percent).
        op: New comparison operator (>, <, >=, <=, ==, !=).
        value: New threshold value.
        host: Target host name or "all".
        severity: Alert severity — info, warning, or critical.
        cooldown_minutes: Minutes before the alert can fire again.
        enabled: Whether the rule is active.

    Returns:
        Confirmation message with updated rule details.
    """
    from ...notifications.conditions import ConditionError, parse_condition
    from .._registry import get_db
    from .create_alert_rule import _format_value

    fields: dict = {}
    condition_parts = [field, op, value]
    condition_provided = [p is not None for p in condition_parts]
    if any(condition_provided):
        if not all(condition_provided):
            return "Error: to change the condition, pass field, op, and value together."
        condition = f"{field} {op} {_format_value(value)}"  # type: ignore[arg-type]
        try:
            parse_condition(condition)
        except ConditionError as e:
            return f"Error: invalid condition: {e}"
        fields["condition"] = condition
    if host is not None:
        fields["host"] = host
    if severity is not None:
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
