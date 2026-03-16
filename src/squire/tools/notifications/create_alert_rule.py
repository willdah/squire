"""Create a new alert rule."""

RISK_LEVEL = 2


async def create_alert_rule(
    name: str,
    condition: str,
    host: str = "all",
    severity: str = "warning",
    cooldown_minutes: int = 30,
) -> str:
    """Create a new alert rule that triggers notifications when a condition is met.

    Args:
        name: Human-readable name for the rule (e.g., "disk-full").
        condition: Condition expression in the format "<field> <op> <value>"
            (e.g., "cpu_percent > 90", "memory_used_mb > 14000").
        host: Host to monitor ("all" for all hosts, or a specific host name).
        severity: Alert severity — "info", "warning", or "critical".
        cooldown_minutes: Minimum minutes between repeated alerts for this rule.

    Returns:
        Confirmation message or error description.
    """
    from ...notifications.conditions import ConditionError, parse_condition
    from .._registry import get_db

    # Validate the condition syntax
    try:
        parse_condition(condition)
    except ConditionError as e:
        return f"Error: {e}"

    if severity not in ("info", "warning", "critical"):
        return f"Error: severity must be 'info', 'warning', or 'critical', got '{severity}'."

    db = get_db()
    if db is None:
        return "Error: database not configured."

    try:
        rule_id = await db.save_alert_rule(
            name=name,
            condition=condition,
            host=host,
            severity=severity,
            cooldown_minutes=cooldown_minutes,
        )
        return f"Alert rule '{name}' created (id={rule_id}): {condition} on host={host}, severity={severity}."
    except Exception as e:
        if "UNIQUE" in str(e):
            return f"Error: an alert rule named '{name}' already exists."
        return f"Error creating alert rule: {e}"
