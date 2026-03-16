"""List configured alert rules."""

RISK_LEVEL = 1


async def list_alert_rules() -> str:
    """List all configured alert rules and their status.

    Returns:
        A formatted list of alert rules, or a message if none exist.
    """
    from .._registry import get_db

    db = get_db()
    if db is None:
        return "Error: database not configured."

    rules = await db.list_alert_rules()
    if not rules:
        return "No alert rules configured."

    lines = []
    for r in rules:
        status = "enabled" if r.get("enabled") else "disabled"
        last = r.get("last_fired_at") or "never"
        lines.append(
            f"- **{r['name']}** [{status}]: `{r['condition']}` "
            f"(host={r['host']}, severity={r['severity']}, "
            f"cooldown={r['cooldown_minutes']}m, last fired: {last})"
        )

    return f"**Alert Rules** ({len(rules)}):\n" + "\n".join(lines)
