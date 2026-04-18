"""Notification tools for the Notifier sub-agent.

Tool for sending ad-hoc webhook notifications. Alerting itself is delegated
to external monitoring stacks (Prometheus/Alertmanager, Grafana, Uptime Kuma).
"""

from .._safe import safe_tool
from .send_notification import RISK_LEVEL as _sn_risk
from .send_notification import send_notification

NOTIFIER_TOOLS = [
    safe_tool(send_notification),
]

NOTIFIER_RISK_LEVELS: dict[str, int] = {
    "send_notification": _sn_risk,
}
