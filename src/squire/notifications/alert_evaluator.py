"""Background alert evaluator — checks alert rules against system snapshots.

Evaluates active alert rules against the latest snapshot data and fires
notifications when conditions are met, respecting cooldown periods.
"""

import logging
from datetime import UTC, datetime, timedelta

from ..database.service import DatabaseService
from .conditions import ConditionError, evaluate_condition, parse_condition
from .router import NotificationRouter

logger = logging.getLogger(__name__)


async def evaluate_alerts(
    db: DatabaseService,
    notifier: NotificationRouter,
    snapshot: dict[str, dict],
) -> int:
    """Evaluate all active alert rules against the current snapshot.

    Args:
        db: Database service for reading rules and updating last_fired.
        notifier: Webhook dispatcher for sending alert notifications.
        snapshot: Multi-host snapshot dict keyed by host name.

    Returns:
        Number of alerts fired.
    """
    rules = await db.get_active_alert_rules()
    if not rules:
        return 0

    fired = 0
    now = datetime.now(UTC)

    for rule in rules:
        try:
            condition = parse_condition(rule["condition"])
        except ConditionError:
            logger.warning("Skipping rule '%s': invalid condition '%s'", rule["name"], rule["condition"])
            continue

        # Check cooldown
        last_fired = rule.get("last_fired_at")
        if last_fired:
            try:
                last_dt = datetime.fromisoformat(last_fired)
                cooldown = timedelta(minutes=rule.get("cooldown_minutes", 30))
                if now - last_dt < cooldown:
                    continue
            except ValueError:
                logger.debug("Malformed last_fired_at for rule '%s': %s", rule["name"], last_fired)

        # Determine which hosts to check
        target_host = rule.get("host", "all")
        hosts_to_check = list(snapshot.keys()) if target_host == "all" else [target_host]

        for host_name in hosts_to_check:
            host_snapshot = snapshot.get(host_name)
            if not host_snapshot or host_snapshot.get("error"):
                continue

            if evaluate_condition(condition, host_snapshot):
                severity = rule.get("severity", "warning")
                summary = f"[{severity.upper()}] Alert '{rule['name']}' triggered on {host_name}: {rule['condition']}"
                await _dispatch_alert(notifier, summary, rule, host_name)
                await db.update_alert_last_fired(rule["name"])
                fired += 1
                break  # One fire per rule per evaluation cycle

    return fired


async def _dispatch_alert(
    notifier: NotificationRouter,
    summary: str,
    rule: dict,
    host: str,
) -> None:
    """Best-effort alert notification dispatch."""
    try:
        await notifier.dispatch(
            category="watch.alert",
            summary=summary,
            details=f"rule={rule['name']}, condition={rule['condition']}, host={host}",
        )
    except Exception:
        logger.debug("Failed to dispatch alert for rule '%s'", rule["name"], exc_info=True)
