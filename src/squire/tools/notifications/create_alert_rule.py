"""Create a new alert rule."""

from typing import Literal

RISK_LEVEL = 2

AlertField = Literal["cpu_percent", "memory_used_mb", "memory_total_mb", "disk_percent"]
AlertOp = Literal[">", "<", ">=", "<=", "==", "!="]
AlertSeverity = Literal["info", "warning", "critical"]


async def create_alert_rule(
    name: str,
    field: AlertField,
    op: AlertOp,
    value: float,
    host: str = "all",
    severity: AlertSeverity = "warning",
    cooldown_minutes: int = 30,
) -> str:
    """Create a new alert rule that fires notifications when a condition is met.

    Args:
        name: Human-readable name for the rule (e.g., "disk-full").
        field: Snapshot field to watch — cpu_percent, memory_used_mb, memory_total_mb, or disk_percent.
        op: Comparison operator — >, <, >=, <=, ==, or !=.
        value: Numeric threshold for the comparison (e.g., 90).
        host: Host to monitor ("all" for every host, or a configured host name).
        severity: Alert severity — info, warning, or critical.
        cooldown_minutes: Minimum minutes between repeated alerts for this rule.

    Returns:
        Confirmation message or error description.
    """
    from ...notifications.conditions import ConditionError, parse_condition
    from .._registry import get_db

    condition = f"{field} {op} {_format_value(value)}"
    try:
        parse_condition(condition)
    except ConditionError as e:
        return f"Error: {e}"

    db = get_db()
    if db is None:
        return "Error: database not configured."

    import sqlite3

    try:
        rule_id = await db.save_alert_rule(
            name=name,
            condition=condition,
            host=host,
            severity=severity,
            cooldown_minutes=cooldown_minutes,
        )
        return f"Alert rule '{name}' created (id={rule_id}): {condition} on host={host}, severity={severity}."
    except sqlite3.IntegrityError:
        return f"Error: an alert rule named '{name}' already exists."
    except (ValueError, sqlite3.Error) as e:
        return f"Error creating alert rule: {e}"


def _format_value(value: float) -> str:
    """Render the threshold without an unnecessary trailing ``.0``."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
