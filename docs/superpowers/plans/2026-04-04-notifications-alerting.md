# Notifications & Alerting Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken alert evaluation, add email notifications, add alert management UI, and improve the Notifier agent so alerts actually work end-to-end.

**Architecture:** A new `NotificationRouter` wraps `WebhookDispatcher` + `EmailNotifier` behind the same `dispatch()` interface. The router replaces the raw dispatcher everywhere. The existing `evaluate_alerts()` function is wired into the watch loop. The `/notifications` page gains tabs for Alert Rules (CRUD) and Channels (webhook + email management), absorbing what was on `/config`.

**Tech Stack:** Python 3.12+ (smtplib, email.mime), FastAPI, Pydantic, React 19, shadcn/ui v4, SWR

**Spec:** `docs/superpowers/specs/2026-04-04-notifications-alerting-design.md`

---

## Task 1: EmailConfig Model

**Files:**
- Modify: `src/squire/config/notifications.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add EmailConfig model**

In `src/squire/config/notifications.py`, after the `WebhookConfig` class (line 21), add:

```python
class EmailConfig(BaseModel):
    """Configuration for email notification delivery."""

    enabled: bool = Field(default=False, description="Whether email notifications are enabled")
    smtp_host: str = Field(default="", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP port (typically 587 for TLS)")
    use_tls: bool = Field(default=True, description="Use STARTTLS for SMTP connection")
    smtp_user: str = Field(default="", description="SMTP authentication username")
    smtp_password: str = Field(default="", description="SMTP authentication password")
    from_address: str = Field(default="", description="Email sender address")
    to_addresses: list[str] = Field(default_factory=list, description="Recipient email addresses")
    events: list[str] = Field(default=["*"], description="Event categories to send (or '*' for all)")
```

Then add an `email` field to `NotificationsConfig`, after the `webhooks` field:

```python
    email: EmailConfig | None = Field(
        default=None,
        description="Email notification configuration",
    )
```

- [ ] **Step 2: Add test for EmailConfig defaults**

In `tests/test_config.py`, add to `TestNotificationsConfig`:

```python
    def test_email_defaults_none(self):
        config = NotificationsConfig()
        assert config.email is None

    def test_email_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {
            "notifications": {
                "enabled": True,
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.example.com",
                    "from_address": "squire@example.com",
                    "to_addresses": ["admin@example.com"],
                },
            }
        })
        config = NotificationsConfig()
        assert config.email is not None
        assert config.email.smtp_host == "smtp.example.com"
        assert config.email.to_addresses == ["admin@example.com"]
```

Note: `TestNotificationsConfig` doesn't have `_patch_toml` — use the pattern from `TestTomlLoading`:
```python
    def test_email_from_toml(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {
            "notifications": {
                "enabled": True,
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.example.com",
                    "from_address": "squire@example.com",
                    "to_addresses": ["admin@example.com"],
                },
            }
        })
        config = NotificationsConfig()
        assert config.email is not None
        assert config.email.smtp_host == "smtp.example.com"
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: All pass including new email tests.

- [ ] **Step 4: Commit**

```bash
git add src/squire/config/notifications.py tests/test_config.py
git commit -m "feat(config): add EmailConfig model for SMTP notifications"
```

---

## Task 2: EmailNotifier Class

**Files:**
- Create: `src/squire/notifications/email.py`
- Create: `tests/test_notifications/test_email.py`

- [ ] **Step 1: Write tests for EmailNotifier**

Create `tests/test_notifications/test_email.py`:

```python
"""Tests for the email notifier."""

from unittest.mock import MagicMock, patch

import pytest

from squire.config.notifications import EmailConfig
from squire.notifications.email import EmailNotifier


@pytest.fixture
def email_config():
    return EmailConfig(
        enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        use_tls=True,
        smtp_user="user@example.com",
        smtp_password="secret",
        from_address="squire@example.com",
        to_addresses=["admin@example.com"],
        events=["*"],
    )


class TestEmailNotifier:
    @pytest.mark.asyncio
    async def test_dispatch_sends_email(self, email_config):
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            await notifier.dispatch(category="watch.alert", summary="CPU high")
            mock_server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_matching_events(self, email_config):
        email_config.events = ["error"]
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            await notifier.dispatch(category="watch.alert", summary="CPU high")
            mock_smtp.SMTP.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_disabled_is_noop(self, email_config):
        email_config.enabled = False
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            await notifier.dispatch(category="watch.alert", summary="CPU high")
            mock_smtp.SMTP.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_no_recipients_is_noop(self, email_config):
        email_config.to_addresses = []
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            await notifier.dispatch(category="watch.alert", summary="test")
            mock_smtp.SMTP.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_error_does_not_raise(self, email_config):
        notifier = EmailNotifier(email_config)
        with patch("squire.notifications.email.smtplib") as mock_smtp:
            mock_smtp.SMTP.side_effect = ConnectionRefusedError("SMTP down")
            await notifier.dispatch(category="watch.alert", summary="test")
            # Should not raise

    @pytest.mark.asyncio
    async def test_wildcard_matches_all_events(self, email_config):
        email_config.events = ["*"]
        notifier = EmailNotifier(email_config)
        assert notifier._matches("watch.alert")
        assert notifier._matches("error")
        assert notifier._matches("anything")

    @pytest.mark.asyncio
    async def test_specific_event_filter(self, email_config):
        email_config.events = ["watch.alert", "error"]
        notifier = EmailNotifier(email_config)
        assert notifier._matches("watch.alert")
        assert notifier._matches("error")
        assert not notifier._matches("watch.start")
```

- [ ] **Step 2: Implement EmailNotifier**

Create `src/squire/notifications/email.py`:

```python
"""Email notification channel using stdlib smtplib."""

import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from email.mime.text import MIMEText

from ..config.notifications import EmailConfig

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send notifications via SMTP email.

    SMTP operations run in an executor to avoid blocking the event loop.
    Failures are logged but never raised.
    """

    def __init__(self, config: EmailConfig) -> None:
        self._config = config

    def _matches(self, category: str) -> bool:
        """Check if a category matches the configured event filter."""
        return "*" in self._config.events or category in self._config.events

    async def dispatch(
        self,
        *,
        category: str,
        summary: str,
        details: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Send an email notification to configured recipients."""
        if not self._config.enabled or not self._config.to_addresses:
            return
        if not self._matches(category):
            return

        subject = f"[Squire] [{category}] {summary}"
        body_parts = [
            f"Category: {category}",
            f"Time: {datetime.now(UTC).isoformat()}",
            f"Summary: {summary}",
        ]
        if details:
            body_parts.append(f"\nDetails:\n{details}")
        if session_id:
            body_parts.append(f"Session: {session_id}")
        if tool_name:
            body_parts.append(f"Tool: {tool_name}")

        body = "\n".join(body_parts)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._send_sync, subject, body)
        except Exception:
            logger.warning("Failed to send email notification", exc_info=True)

    def _send_sync(self, subject: str, body: str) -> None:
        """Blocking SMTP send — called from executor."""
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._config.from_address
        msg["To"] = ", ".join(self._config.to_addresses)

        with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as server:
            if self._config.use_tls:
                server.starttls()
            if self._config.smtp_user and self._config.smtp_password:
                server.login(self._config.smtp_user, self._config.smtp_password)
            server.send_message(msg)

    async def close(self) -> None:
        """No persistent connection to clean up."""
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_notifications/test_email.py -v`
Expected: All 7 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/squire/notifications/email.py tests/test_notifications/test_email.py
git commit -m "feat(notifications): add EmailNotifier with SMTP support"
```

---

## Task 3: NotificationRouter

**Files:**
- Create: `src/squire/notifications/router.py`
- Create: `tests/test_notifications/test_router.py`
- Modify: `src/squire/notifications/__init__.py`

- [ ] **Step 1: Write tests for NotificationRouter**

Create `tests/test_notifications/test_router.py`:

```python
"""Tests for the notification router."""

from unittest.mock import AsyncMock

import pytest

from squire.notifications.router import NotificationRouter


@pytest.fixture
def mock_webhook():
    return AsyncMock()


@pytest.fixture
def mock_email():
    return AsyncMock()


class TestNotificationRouter:
    @pytest.mark.asyncio
    async def test_dispatches_to_webhook(self, mock_webhook):
        router = NotificationRouter(webhook=mock_webhook)
        await router.dispatch(category="test", summary="hello")
        mock_webhook.dispatch.assert_called_once_with(
            category="test", summary="hello", details=None, session_id=None, tool_name=None,
        )

    @pytest.mark.asyncio
    async def test_dispatches_to_email(self, mock_webhook, mock_email):
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.dispatch(category="test", summary="hello")
        mock_email.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_email_is_fine(self, mock_webhook):
        router = NotificationRouter(webhook=mock_webhook)
        await router.dispatch(category="test", summary="hello")
        # No error, only webhook called

    @pytest.mark.asyncio
    async def test_webhook_error_does_not_block_email(self, mock_webhook, mock_email):
        mock_webhook.dispatch.side_effect = Exception("webhook down")
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.dispatch(category="test", summary="hello")
        mock_email.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_error_does_not_block(self, mock_webhook, mock_email):
        mock_email.dispatch.side_effect = Exception("smtp down")
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.dispatch(category="test", summary="hello")
        mock_webhook.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_delegates(self, mock_webhook, mock_email):
        router = NotificationRouter(webhook=mock_webhook, email=mock_email)
        await router.close()
        mock_webhook.close.assert_called_once()
        mock_email.close.assert_called_once()
```

- [ ] **Step 2: Implement NotificationRouter**

Create `src/squire/notifications/router.py`:

```python
"""Notification router — dispatches to all configured channels."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotificationRouter:
    """Routes notifications to webhook and email channels.

    Drop-in replacement for WebhookDispatcher — same ``dispatch()`` interface.
    Failures in one channel do not block others.
    """

    def __init__(self, webhook: Any, email: Any | None = None) -> None:
        self._webhook = webhook
        self._email = email

    async def dispatch(
        self,
        *,
        category: str,
        summary: str,
        details: str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Send to all configured channels. Failures are logged, never raised."""
        kwargs = dict(category=category, summary=summary, details=details, session_id=session_id, tool_name=tool_name)

        try:
            await self._webhook.dispatch(**kwargs)
        except Exception:
            logger.warning("Webhook dispatch failed", exc_info=True)

        if self._email is not None:
            try:
                await self._email.dispatch(**kwargs)
            except Exception:
                logger.warning("Email dispatch failed", exc_info=True)

    async def close(self) -> None:
        """Clean up all channel resources."""
        await self._webhook.close()
        if self._email is not None:
            await self._email.close()
```

- [ ] **Step 3: Update `__init__.py`**

Replace `src/squire/notifications/__init__.py`:

```python
from .email import EmailNotifier
from .router import NotificationRouter
from .webhook import WebhookDispatcher

__all__ = ["EmailNotifier", "NotificationRouter", "WebhookDispatcher"]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_notifications/ -v`
Expected: All tests pass (existing webhook + new router + new email).

- [ ] **Step 5: Commit**

```bash
git add src/squire/notifications/router.py src/squire/notifications/__init__.py tests/test_notifications/test_router.py
git commit -m "feat(notifications): add NotificationRouter to dispatch across channels"
```

---

## Task 4: Integrate Router into App and Watch Loop

**Files:**
- Modify: `src/squire/api/app.py`
- Modify: `src/squire/api/dependencies.py`
- Modify: `src/squire/watch.py`

- [ ] **Step 1: Update dependencies.py**

Change the import and type hint for `notifier`:
- Replace `from squire.notifications.webhook import WebhookDispatcher` with `from squire.notifications.router import NotificationRouter`
- Change `notifier: WebhookDispatcher | None = None` to `notifier: NotificationRouter | None = None`
- Update `get_notifier()` return type and error message to `NotificationRouter`

- [ ] **Step 2: Update app.py lifespan**

In the lifespan function, after creating `WebhookDispatcher`, wrap it with `NotificationRouter`:

```python
    from squire.notifications.email import EmailNotifier
    from squire.notifications.router import NotificationRouter

    webhook_dispatcher = WebhookDispatcher(deps.notif_config)
    email_notifier = None
    if deps.notif_config.email and deps.notif_config.email.enabled:
        email_notifier = EmailNotifier(deps.notif_config.email)
    deps.notifier = NotificationRouter(webhook=webhook_dispatcher, email=email_notifier)
```

- [ ] **Step 3: Wire evaluate_alerts into watch.py**

In `watch.py`, find the snapshot collection block (after `await db.save_snapshot(...)`) and add alert evaluation. Import `evaluate_alerts` at the top of the file. After snapshot save and before the agent check-in:

```python
    # Evaluate alert rules against fresh snapshot
    try:
        fired = await evaluate_alerts(db, notifier, snapshot)
        if fired > 0 and emitter:
            await emitter.emit_tool_result(cycle, "alert_evaluator", f"{fired} alert(s) fired")
    except Exception:
        logger.debug("Alert evaluation failed", exc_info=True)
```

Also update watch.py's notifier initialization to use `NotificationRouter` instead of `WebhookDispatcher` directly — same pattern as app.py.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass. Existing watch tests use mocked notifier so the type change is transparent.

- [ ] **Step 5: Commit**

```bash
git add src/squire/api/app.py src/squire/api/dependencies.py src/squire/watch.py
git commit -m "feat(notifications): wire NotificationRouter and alert evaluator into app and watch loop"
```

---

## Task 5: update_alert_rule Tool + Notifier Instructions

**Files:**
- Create: `src/squire/tools/notifications/update_alert_rule.py`
- Modify: `src/squire/tools/notifications/__init__.py`
- Modify: `src/squire/instructions/notifier_agent.py`

- [ ] **Step 1: Create update_alert_rule tool**

Create `src/squire/tools/notifications/update_alert_rule.py`:

```python
"""Update an existing alert rule."""

RISK_LEVEL = 2

from .._registry import get_db


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
    db = get_db()

    fields: dict = {}
    if condition is not None:
        from ...notifications.conditions import ConditionError, parse_condition

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

    updated = await db.update_alert_rule(name, **fields)
    if not updated:
        return f"Error: alert rule '{name}' not found"

    return f"Updated alert rule '{name}': {', '.join(f'{k}={v}' for k, v in fields.items())}"
```

- [ ] **Step 2: Register in __init__.py**

In `src/squire/tools/notifications/__init__.py`, add the import and register:

```python
from .update_alert_rule import update_alert_rule

# Add to NOTIFIER_TOOLS list:
    safe_tool(update_alert_rule),

# Add to NOTIFIER_RISK_LEVELS dict:
    "update_alert_rule": update_alert_rule.RISK_LEVEL,
```

Follow the exact pattern used by the other tools in the file — import the module's `RISK_LEVEL`, add `safe_tool(update_alert_rule)` to the list, add the risk level to the dict.

- [ ] **Step 3: Update Notifier agent instructions**

Replace the tool usage section in `src/squire/instructions/notifier_agent.py` with improved guidance:

```python
## Tool Usage
- Use `list_alert_rules` to show the user their current alert rules.
- Use `create_alert_rule` to set up new alerts. Conditions use the format: `<field> <op> <value>`.
  Fields: `cpu_percent`, `memory_used_mb`, `memory_total_mb`, `disk_percent`.
  Operators: `>`, `<`, `>=`, `<=`, `==`, `!=`.
  Examples: `cpu_percent > 90`, `memory_used_mb > 14000`, `disk_percent > 85`.
- Use `update_alert_rule` to modify existing rules (change condition, severity, host, cooldown, or enable/disable).
- Use `delete_alert_rule` to remove rules the user no longer wants.
- Use `send_notification` to send a test or ad-hoc notification.
- Alert conditions evaluate against periodic system snapshots (CPU, memory, disk, container state).
  Event-based monitoring (e.g. "alert me when a container restarts") requires an external tool
  like Grafana or Uptime Kuma sending alerts to Squire. Be honest about this limitation.
- When the user requests an action, call the tool directly. Do NOT ask for confirmation
  — the risk gate handles approval for dangerous actions via a UI dialog automatically.
- If a tool fails or is blocked, report the error and continue responding.
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest -v`
Expected: All pass. The new tool follows existing patterns so no new tool test is strictly needed (the DB method is already tested), but the tool will be exercised via integration.

- [ ] **Step 5: Commit**

```bash
git add src/squire/tools/notifications/update_alert_rule.py src/squire/tools/notifications/__init__.py src/squire/instructions/notifier_agent.py
git commit -m "feat(tools): add update_alert_rule tool and improve Notifier instructions"
```

---

## Task 6: Test Email Endpoint

**Files:**
- Create: `src/squire/api/routers/notifications.py`
- Modify: `src/squire/api/app.py` (register router)

- [ ] **Step 1: Create notifications router with test-email endpoint**

Create `src/squire/api/routers/notifications.py`:

```python
"""Notification management endpoints."""

from fastapi import APIRouter, HTTPException

from .. import dependencies as deps

router = APIRouter()


@router.post("/test-email")
async def test_email():
    """Send a test email using the current email configuration."""
    notifier = deps.get_notifier()
    email = getattr(notifier, "_email", None)
    if email is None:
        raise HTTPException(status_code=400, detail="Email notifications are not configured")

    try:
        await email.dispatch(
            category="test",
            summary="Test email from Squire",
            details="If you received this, email notifications are working correctly.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {e}")

    return {"status": "ok", "message": "Test email sent"}
```

- [ ] **Step 2: Register router in app.py**

In `src/squire/api/app.py`, add alongside the other router imports and registrations:

```python
from .routers import notifications as notifications_router
app.include_router(notifications_router.router, prefix="/api/notifications", tags=["notifications"])
```

- [ ] **Step 3: Run tests and lint**

Run: `uv run pytest -v && uv run ruff check src/ tests/`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/squire/api/routers/notifications.py src/squire/api/app.py
git commit -m "feat(api): add POST /api/notifications/test-email endpoint"
```

---

## Task 7: Email Password Redaction in Config API

**Files:**
- Modify: `src/squire/api/routers/config.py`

- [ ] **Step 1: Update _redact_notifications to handle email**

In `src/squire/api/routers/config.py`, update the `_redact_notifications` function:

```python
def _redact_notifications(data: dict) -> dict:
    """Redact webhook URLs, auth headers, and email password."""
    for wh in data.get("webhooks", []):
        if wh.get("url"):
            wh["url"] = _REDACTED
        if wh.get("headers"):
            wh["headers"] = {k: _REDACTED for k in wh["headers"]}
    email = data.get("email")
    if email and isinstance(email, dict):
        if email.get("smtp_password"):
            email["smtp_password"] = _REDACTED
    return data
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_config_api.py -v`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add src/squire/api/routers/config.py
git commit -m "fix(config): redact email smtp_password in config API responses"
```

---

## Task 8: Frontend — Alert Rules Tab

**Files:**
- Create: `web/src/components/notifications/alert-rule-form.tsx`
- Create: `web/src/components/notifications/alert-rules-tab.tsx`
- Modify: `web/src/lib/types.ts`

- [ ] **Step 1: Add AlertRule TypeScript types**

In `web/src/lib/types.ts`, add (matching the existing Python `AlertRule` schema):

```typescript
export interface AlertRule {
  id?: number;
  name: string;
  condition: string;
  host: string;
  severity: string;
  cooldown_minutes: number;
  last_fired_at?: string | null;
  enabled: boolean;
  created_at?: string;
}

export interface AlertRuleCreate {
  name: string;
  condition: string;
  host?: string;
  severity?: string;
  cooldown_minutes?: number;
}
```

- [ ] **Step 2: Create alert rule form dialog**

Create `web/src/components/notifications/alert-rule-form.tsx` — a Dialog with fields for name, condition, host (select), severity (select), and cooldown. Supports both create and edit modes. Follow the pattern from `web/src/components/skills/skill-form.tsx` (Dialog with local state, validation, submit handler).

Key fields:
- Name: text input, disabled when editing, validated (lowercase alphanumeric + hyphens)
- Condition: text input, placeholder `cpu_percent > 90`
- Host: select with "all" + dynamically fetched hosts from `/api/hosts`
- Severity: select with info/warning/critical
- Cooldown: number input, default 30

- [ ] **Step 3: Create alert rules tab**

Create `web/src/components/notifications/alert-rules-tab.tsx` — a table listing all alert rules with inline toggle switch and edit/delete actions. Uses SWR to fetch from `GET /api/alerts`. Mutations use `apiPost`, `apiPut`, `apiDelete` and call `mutate()` to refresh.

Follow the CRUD pattern from `web/src/app/skills/page.tsx` (table with actions, dialog for create/edit, confirmation for delete).

- [ ] **Step 4: Verify build**

Run: `cd web && npm run build`
Expected: Compiles without errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/types.ts web/src/components/notifications/alert-rule-form.tsx web/src/components/notifications/alert-rules-tab.tsx
git commit -m "feat(web): add Alert Rules tab with CRUD for /notifications page"
```

---

## Task 9: Frontend — Channels Tab

**Files:**
- Create: `web/src/components/notifications/channels-tab.tsx`

- [ ] **Step 1: Create channels tab**

Create `web/src/components/notifications/channels-tab.tsx` — the fully editable channels management panel. Layout:

1. Master enable/disable switch at the top
2. **Webhooks section**: card list of configured webhooks with add/edit/delete. Uses the same PATCH `/api/config/notifications` endpoint. Webhook URLs shown redacted for existing entries, editable for new ones. Events as tag input.
3. **Email section**: form card with SMTP host, port, TLS toggle, from address, to addresses (tag input), events filter. Test email button calls `POST /api/notifications/test-email`.
4. All mutations via `apiPatch("/api/config/notifications", ...)` with `?persist=true`.

Follow the pattern from the existing `notifications-config-form.tsx` for webhook management, and extend with the email config section.

- [ ] **Step 2: Verify build**

Run: `cd web && npm run build`
Expected: Compiles.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/notifications/channels-tab.tsx
git commit -m "feat(web): add Channels tab with webhook and email management"
```

---

## Task 10: Frontend — Assemble /notifications Page with Tabs

**Files:**
- Modify: `web/src/app/notifications/page.tsx`
- Modify: `web/src/components/notifications/notification-history.tsx`
- Modify: `web/src/components/config/config-editor.tsx`
- Delete: `web/src/components/config/notifications-config-form.tsx`

- [ ] **Step 1: Add category filter to notification history**

In `web/src/components/notifications/notification-history.tsx`, add a category filter dropdown above the table. The dropdown options: All, watch.alert, watch.blocked, watch.start, watch.stop, error. Filter the events list before rendering.

- [ ] **Step 2: Rewrite notifications page with tabs**

Rewrite `web/src/app/notifications/page.tsx` to use `Tabs`/`TabsList`/`TabsTrigger`/`TabsContent` (same pattern as `/config` page):

```tsx
<Tabs defaultValue="history">
  <TabsList>
    <TabsTrigger value="history">History</TabsTrigger>
    <TabsTrigger value="rules">Alert Rules</TabsTrigger>
    <TabsTrigger value="channels">Channels</TabsTrigger>
  </TabsList>
  <TabsContent value="history">
    <NotificationHistory events={...} />
  </TabsContent>
  <TabsContent value="rules">
    <AlertRulesTab />
  </TabsContent>
  <TabsContent value="channels">
    <ChannelsTab />
  </TabsContent>
</Tabs>
```

- [ ] **Step 3: Remove notifications tab from /config**

In `web/src/components/config/config-editor.tsx`:
- Remove the `<TabsTrigger value="notifications">` and its `<TabsContent>`
- Remove the import of `NotificationsConfigForm`

Delete `web/src/components/config/notifications-config-form.tsx`.

- [ ] **Step 4: Verify build**

Run: `cd web && npm run build`
Expected: Compiles.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/notifications/page.tsx web/src/components/notifications/ web/src/components/config/config-editor.tsx
git rm web/src/components/config/notifications-config-form.tsx
git commit -m "feat(web): assemble /notifications page with History, Alert Rules, and Channels tabs

Notifications config moves from /config to /notifications as the single
source of truth for all notification settings."
```

---

## Task 11: CHANGELOG and Final Verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CHANGELOG**

Add under `## [Unreleased]` → `### Added`:

```markdown
- **Notifications & alerting overhaul** — alerts actually fire and email notifications are supported
  - Wired `evaluate_alerts()` into the watch loop — alert rules now trigger automatically during watch cycles
  - Email notification channel via SMTP alongside existing webhooks, configured in `squire.toml` under `[notifications.email]`
  - `NotificationRouter` dispatches to all configured channels (webhooks + email)
  - `update_alert_rule` LLM tool — the Notifier agent can now modify and toggle existing alert rules
  - `POST /api/notifications/test-email` endpoint for verifying email configuration
  - `/notifications` page expanded with three tabs: History (with category filter), Alert Rules (full CRUD), and Channels (webhook + email management)
  - Improved Notifier agent instructions with condition syntax examples and honest capability boundaries
```

Add under `### Changed`:
```markdown
- Notification channel management moved from `/config` to `/notifications` page as the single source of truth
- `deps.notifier` is now a `NotificationRouter` instead of `WebhookDispatcher` (same `dispatch()` interface)
```

- [ ] **Step 2: Run full verification**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pytest
cd web && npm run build
```

All must pass.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for notifications & alerting overhaul"
```
