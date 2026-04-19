# Watch Mode

Watch mode is Squire's autonomous homelab monitor and remediation loop. It runs recurring cycles that:

1. detect incidents,
2. generate RCA and an action plan,
3. execute remediations through tool calls, and
4. verify outcomes.

## Incident Inbox

Use the web `Incidents` page as the primary operator surface.

- **Needs you**: incidents with pending tool approvals or escalations.
- **Active**: incidents currently being handled.
- **Recently resolved**: recent successful remediations (collapsed by default).

Each incident groups repeated cycles by a stable `incident_key` fingerprint and links to `Activity` for raw event history.

## Autonomy Modes

Watch now has a global autonomy mode:

- `supervised` (default): watch requests approval for configured approval tools and high-risk escalations.
- `autonomous`: watch raises effective risk tolerance (up to high-risk) and disables configured approval-tool prompts, while still honoring deny lists and critical/pattern escalation behavior.

API:

- `GET /api/watch/mode`
- `POST /api/watch/mode` with `{"mode":"supervised"|"autonomous"}`

## Approval Flow

Watch uses a DB-backed approval provider:

- approval requests are persisted in `watch_approvals`,
- emitted as watch events for UI/live stream visibility,
- remain actionable from the incident inbox,
- expire after `watch.approval_timeout_seconds` (default `300`),
- emit a reminder event at 60 seconds.

Relevant config:

- `watch.autonomy_mode` (`supervised` | `autonomous`)
- `watch.approval_timeout_seconds` (int, default `300`)
- `watch.max_autonomous_actions_per_hour` (int, default `30`) — cross-cycle ceiling on auto-approved actions; above the ceiling, actions downgrade to `NEEDS_APPROVAL`.
- `watch.insight_sweep_interval_hours` (int, default `6`) — cadence for the proactive insight sweep.

## Security Foundations (Phase 1)

These apply in both supervised and autonomous modes:

- **Tool-output sanitization.** Before tool output flows back into the LLM, it is stripped of ANSI escapes, control characters, and instruction-shaped text (e.g. `IGNORE PREVIOUS INSTRUCTIONS`, `<system>` tags), then wrapped in `<tool-output source="..."></tool-output>` envelopes. This is the primary defense against prompt injection from untrusted logs.
- **Persistent kill switch.** `POST /api/watch/kill-switch` with `{"active": true}` halts autonomy across cycles; the flag survives restart. The `/incidents` header has a one-click toggle.
- **Autonomous rate ceiling.** `watch.max_autonomous_actions_per_hour` caps auto-approved tool calls per rolling hour. Exceeding the ceiling emits a `rate_limit` event and downgrades the next action to `NEEDS_APPROVAL`.
- **Tamper-evident audit chain.** `watch_events` rows carry a SHA-256 hash chain (`prev_hash`, `content_hash`). `GET /api/watch/audit/verify` walks the chain and reports mismatches — it also records any break into `audit_breaks` so deletions remain visible.

## Incident Lifecycle (Phase 2)

Each recurring incident is a durable row in the `incidents` table, overlaid onto the cycle-derived view:

- `POST /api/watch/incidents/{key}/ack`
- `POST /api/watch/incidents/{key}/snooze` (default 1h, or `{"duration_seconds": N}`)
- `POST /api/watch/incidents/{key}/resolve`

Snoozed incidents keep detecting but suppress notifications until `snoozed_until`.

## Skill Autonomy Metadata (Phase 2)

Skills (`SKILL.md`) can declare per-skill autonomy under the `metadata` frontmatter key:

```yaml
metadata:
  trigger: watch
  autonomy: propose        # observe | remediate | propose (default: propose)
  allowed_tools: [docker_container, run_command]
  category: reliability    # reliability | maintenance | security | design
```

- `observe` — read-only; write tools are stripped for the cycle.
- `remediate` — auto-executes its `allowed_tools` even in supervised mode. Load-time log warning surfaces these.
- `propose` (default) — forces approval for the skill's `allowed_tools` even in autonomous mode.

## Trust Affordances (Phase 3)

- **Approval preview.** Approval-request events now include a `preview` object with the tool's effect (`read`/`write`/`mixed`) plus a command summary.
- **Reversible actions.** `reversible_actions` records pre-state snapshots for a curated set of tools. `POST /api/watch/incidents/{key}/revert-last` walks back the most recent snapshot for an incident. Handlers register via `squire.callbacks.revertible.register_revertible`.
- **Simulation.** `POST /api/watch/simulate` runs incident detection against a user-supplied snapshot without touching tools.
- **Autonomous digest.** `GET /api/watch/digest` rolls up actions taken over the last window for scan-from-bed review.

## Proactive Surfaces (Phase 4)

One `/insights` page with four tabs, each reading from the `insights` table filtered by category. Deep-link via `?category=reliability|maintenance|security|design`:

- **Reliability** — MTTR trends, repeat incidents, auto-resolve rate.
- **Maintenance** — patch/upgrade proposals, backup freshness.
- **Security** — exposed services, privilege drift, audit-chain state.
- **Design** — capacity trends, integration suggestions, architecture hardening.

### How insights are generated

Two sources populate the `insights` table automatically on the cadence configured by `watch.insight_sweep_interval_hours` (default `6`). The FastAPI lifespan starts a background task at boot; `POST /api/watch/insights/sweep` also runs both sources manually.

1. **Metric rules** (`insight_sweep_from_metrics`) — deterministic observations over existing telemetry: auto-resolve rate, rate-ceiling hits, audit-chain state, approval latency.

2. **Observe-tier skills** — any enabled skill with `metadata.autonomy: observe` and a recognized `metadata.category` (`reliability`, `maintenance`, `security`, `design`) is run through an insight agent. The skill's instructions are sent as a prompt along with the latest snapshot and 24h metrics; the agent has **no tools**, so skills reason over the provided context only (tool-backed skills are a follow-up).

Skills emit structured output that the sweep parses:

```
INSIGHT: severity=<low|medium|high|critical> summary="<short statement>" detail="<optional>" host="<optional>"
```

Values may be quoted (for spaces) or unquoted (terminate at next `key=` or EOL). One insight per line. Invalid severity or category drops the line. Summaries dedupe via upsert by `(category, summary, host)`.

## Effectiveness Metrics

`GET /api/watch/metrics?hours=24` returns:

- `auto_resolve_rate` — fraction of resolved incidents that did not require approval
- `median_mttr_seconds` — incident first-seen to cycle-ended-at
- `median_approval_latency_seconds` — approval request to response
- `rate_limit_hits` — autonomous rate-ceiling breaches in the window

The `/incidents` header surfaces these as a compact strip.
