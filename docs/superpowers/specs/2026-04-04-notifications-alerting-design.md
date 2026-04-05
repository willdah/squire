# Notifications & Alerting Overhaul

**Date:** 2026-04-04
**Status:** Draft
**Scope:** Phase 1 (implement) + Phase 2 (spec only)

## Context

Squire's alerting system has significant gaps. Alert rules can be created and stored but never fire because the evaluator isn't wired into the watch loop. The Notifier agent lacks an update tool. The web UI has no alert rule management. Notifications only support webhooks — no email. Users report the LLM can't create alerts for common scenarios and falls back to generic guidance.

Rather than building Squire into a full monitoring stack, this design positions Squire as an **alert response engine**: it handles simple threshold alerts natively, but for serious monitoring it receives alerts from external tools (Grafana, Alertmanager, Uptime Kuma) and responds with investigation, remediation, and enriched notifications — governed by the user's risk tolerance.

## Phase 1: Fix the Foundation

### 1.1 Wire Alert Evaluator into Watch Loop

**Problem:** `evaluate_alerts()` in `alert_evaluator.py` is fully implemented but never called.

**Fix:** In `watch.py`, after each snapshot is collected and saved to the DB, call:
```python
from squire.notifications.alert_evaluator import evaluate_alerts
fired = await evaluate_alerts(db, notifier, snapshot)
```

The evaluator:
- Iterates enabled alert rules from the DB
- Parses conditions against the snapshot dict
- Respects per-rule cooldown periods
- Dispatches notifications via the configured channels
- Updates `last_fired_at` timestamps
- Returns count of fired alerts (logged as a watch event)

**Placement:** After `_collect_and_save_snapshot()`, before the agent check-in prompt injection. This ensures alert notifications go out even if the agent's turn fails.

### 1.2 Email Notification Channel

**Architecture:** Add `EmailNotifier` alongside `WebhookDispatcher`. Both are orchestrated by a new `NotificationRouter` that replaces direct dispatcher usage.

**Configuration** (`squire.toml`):
```toml
[notifications]
enabled = true

[notifications.email]
enabled = true
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "squire@example.com"
smtp_password = "app-password"
use_tls = true
from_address = "squire@example.com"
to_addresses = ["will@example.com"]
events = ["watch.alert", "error"]
```

Env var override: `SQUIRE_NOTIFICATIONS_EMAIL_PASSWORD` for the password (avoids plaintext in TOML).

**New files:**
- `src/squire/config/notifications.py` — add `EmailConfig` model to existing file
- `src/squire/notifications/email.py` — `EmailNotifier` class using stdlib `smtplib` + `email.mime`. SMTP operations run via `asyncio.get_event_loop().run_in_executor(None, ...)` to avoid blocking the event loop.
- `src/squire/notifications/router.py` — `NotificationRouter` dispatches to all configured channels

**Integration:** `deps.notifier` changes from `WebhookDispatcher` to `NotificationRouter`. The router holds a list of channel instances (webhook dispatcher + email notifier if configured). All existing `notifier.dispatch()` calls work unchanged.

**Sensitive fields:** `smtp_password` is redacted in `GET /api/config` using the existing `_REDACTED` sentinel. The `PATCH /api/config/notifications` endpoint strips redacted values.

### 1.3 Alert Rule Update Tool

**New tool:** `update_alert_rule` in `src/squire/tools/notifications/`

```python
@safe_tool
async def update_alert_rule(
    name: str,
    condition: str | None = None,
    host: str | None = None,
    severity: str | None = None,
    cooldown_minutes: int | None = None,
    enabled: bool | None = None,
) -> str:
```

Risk level: 2 (same as create). Uses existing `db.update_alert_rule()`.

**Register** in `src/squire/tools/notifications/__init__.py` alongside existing tools.

### 1.4 Notifier Agent Instructions

Update `src/squire/instructions/notifier_agent.py` to:

- List all 4 available tools: `create_alert_rule`, `list_alert_rules`, `update_alert_rule`, `delete_alert_rule`
- Explain condition syntax with examples: `cpu_percent > 90`, `memory_used_mb > 14000`, `disk_percent > 85`
- List available fields: `cpu_percent`, `memory_used_mb`, `memory_total_mb`, `disk_percent`, `uptime`, container states
- Clarify that conditions evaluate against periodic snapshots — event-based monitoring (container restarts between snapshots) requires external tools
- When a user asks for something conditions can't express, be honest and suggest alternatives

### 1.5 Expanded /notifications Page

**Layout:** Three tabs using the existing `Tabs` component.

**Tab 1: History** (existing, polished)
- Current notification event table
- Add category filter dropdown (all, watch.alert, watch.blocked, error, user)
- Auto-refresh at 15s (existing)

**Tab 2: Alert Rules** (new)
- Table: Name, Condition, Host, Severity, Enabled (switch), Last Fired, Actions (edit/delete)
- "New Rule" button opens a dialog with:
  - Name (text input, validated: lowercase alphanumeric + hyphens)
  - Condition (text input, placeholder: `cpu_percent > 90`)
  - Host (select: "all" + available hosts from `/api/hosts`)
  - Severity (select: info / warning / critical)
  - Cooldown minutes (number input, default 30)
- Edit opens the same dialog pre-populated
- Toggle enabled/disabled via inline switch (calls `POST /api/alerts/{name}/toggle`)
- Delete with confirmation dialog

**Tab 3: Channels** (new, informational)
- Card per configured channel showing: type (webhook/email), name, status (enabled/disabled), event filter
- "Configure" link to `/config` (notifications tab)
- Read-only — full editing stays on `/config`

**Data fetching:**
- History: `GET /api/events?limit=200` (existing)
- Alert rules: `GET /api/alerts` (existing)
- Channels: extracted from `GET /api/config` response (existing)

**Mutations:**
- Create: `POST /api/alerts`
- Update: `PUT /api/alerts/{name}`
- Toggle: `POST /api/alerts/{name}/toggle`
- Delete: `DELETE /api/alerts/{name}`

All endpoints already exist.

---

## Phase 2: Incoming Alerts + Autonomous Response (Spec Only)

### 2.1 Incoming Alert Endpoint

**Endpoint:** `POST /api/alerts/incoming`

**Common payload:**
```json
{
  "source": "grafana",
  "title": "High CPU on prod-apps-01",
  "message": "CPU at 95% for 5 minutes",
  "severity": "warning",
  "host": "prod-apps-01",
  "labels": { "alertname": "HighCPU", "instance": "10.20.0.100" }
}
```

**Payload adapters:** Normalize raw payloads from common tools:
- **Alertmanager** — parse `alerts[].labels`, `alerts[].annotations`, `alerts[].status`
- **Grafana** — parse `title`, `message`, `tags`, `state`
- **Generic JSON** — use the common payload format directly

Adapter selection: `source` field hint, or auto-detect from payload structure.

**Authentication:** Optional bearer token configured in `squire.toml`:
```toml
[notifications.incoming]
enabled = true
token = "secret-token"
```

### 2.2 Alert Response Pipeline

When an incoming alert arrives:

1. **Log** the alert as an event in the database
2. **Forward** to configured notification channels (email + webhooks) immediately
3. **Investigate** (if risk tolerance >= `cautious`):
   - Create an ephemeral agent session
   - Inject alert context as a system message
   - Let the agent use read-only tools (system_info, docker_ps, docker_logs, journalctl) to gather context
   - Collect the agent's findings
4. **Remediate** (if risk tolerance >= `standard`):
   - If an alert-triggered skill is configured, execute it
   - Otherwise, let the agent decide (bounded by risk gate as usual)
5. **Notify** with enriched context:
   - Original alert + agent's investigation summary + actions taken
   - Sent to all configured channels

**Risk tolerance governs behavior:**

| Level | Behavior |
|---|---|
| `read-only` (1) | Log + forward notification only |
| `cautious` (2) | Above + investigate with read-only tools |
| `standard` (3) | Above + attempt safe remediation |
| `full-trust` (5) | Above + aggressive remediation allowed |

### 2.3 Alert-Triggered Skills

Alert rules gain an optional `skill` field:
```json
{
  "name": "high-cpu-alert",
  "condition": "cpu_percent > 95",
  "host": "prod-apps-01",
  "severity": "critical",
  "skill": "investigate-high-cpu"
}
```

When this alert fires (from the evaluator or an incoming webhook matching the labels), Squire executes the named skill in the context of the alert. This enables user-defined remediation playbooks:
- "When CPU is high, check top processes and restart the offending container"
- "When disk is full, prune Docker images and notify me"

### 2.4 Incoming Alert UI

Add to the /notifications History tab:
- Incoming alerts shown with a distinct badge ("External" or source name)
- Expandable row showing: original alert, investigation summary, actions taken
- Filter by source

---

## Files to Modify (Phase 1)

| File | Change |
|---|---|
| `src/squire/watch.py` | Call `evaluate_alerts()` after snapshot collection |
| `src/squire/config/notifications.py` | Add `EmailConfig` model |
| `src/squire/notifications/email.py` | New `EmailNotifier` class |
| `src/squire/notifications/router.py` | New `NotificationRouter` class |
| `src/squire/notifications/__init__.py` | Export new classes |
| `src/squire/api/app.py` | Initialize `NotificationRouter` instead of `WebhookDispatcher` |
| `src/squire/api/dependencies.py` | Change `notifier` type hint |
| `src/squire/api/routers/config.py` | Redact email password in GET, handle in PATCH |
| `src/squire/tools/notifications/__init__.py` | Add `update_alert_rule` tool |
| `src/squire/instructions/notifier_agent.py` | Improve instructions with tool list + condition examples |
| `web/src/app/notifications/page.tsx` | Add tabs, integrate alert rules and channels |
| `web/src/components/notifications/alert-rules-tab.tsx` | New: alert rule CRUD table |
| `web/src/components/notifications/alert-rule-form.tsx` | New: create/edit dialog |
| `web/src/components/notifications/channels-tab.tsx` | New: channel overview cards |
| `web/src/lib/types.ts` | Add AlertRule types |
| `tests/test_notifications/` | Tests for email notifier, router, evaluator integration |
| `tests/test_config_api.py` | Email password redaction tests |
| `CHANGELOG.md` | Update |

## Verification (Phase 1)

1. `make test` — all tests pass
2. `make lint` — clean
3. `make web-build` — frontend compiles
4. Manual — watch mode:
   - Create an alert rule (`cpu_percent > 0` for easy testing)
   - Start watch mode
   - Verify alert fires and notification dispatches
5. Manual — web UI:
   - Navigate to `/notifications`
   - Create, edit, toggle, delete alert rules via the Alert Rules tab
   - Verify Channels tab shows configured webhooks/email
6. Manual — chat:
   - Ask Squire to create an alert rule
   - Ask Squire to list and update rules
   - Ask for an impossible alert (container restart) — verify honest response
7. Manual — email:
   - Configure SMTP in `squire.toml`
   - Trigger an alert, verify email received
