"""Notification tools for the Notifier sub-agent.

Tools for managing alert rules and sending notifications.
"""

from .._safe import safe_tool
from .create_alert_rule import RISK_LEVEL as _car_risk
from .create_alert_rule import create_alert_rule
from .delete_alert_rule import RISK_LEVEL as _dar_risk
from .delete_alert_rule import delete_alert_rule
from .list_alert_rules import RISK_LEVEL as _lar_risk
from .list_alert_rules import list_alert_rules
from .send_notification import RISK_LEVEL as _sn_risk
from .send_notification import send_notification

NOTIFIER_TOOLS = [
    safe_tool(send_notification),
    safe_tool(list_alert_rules),
    safe_tool(create_alert_rule),
    safe_tool(delete_alert_rule),
]

NOTIFIER_RISK_LEVELS: dict[str, int] = {
    "send_notification": _sn_risk,
    "list_alert_rules": _lar_risk,
    "create_alert_rule": _car_risk,
    "delete_alert_rule": _dar_risk,
}
