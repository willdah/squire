# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Watch mode in Docker containers:** Watch no longer becomes "lost" after navigating away from the watch page, and subsequent starts reliably reach `running`. The previous subprocess model spawned the watch loop via `subprocess.Popen` with `stderr=DEVNULL`, so failures were invisible; inside a container, PID reuse in the PID namespace could also make `os.kill(pid, 0)` return false positives, freezing the UI in a stale "running" state that couldn't be restarted. Root cause was architectural, not a single bug — the fix is the refactor below.

### Changed

- **Watch mode architecture:** Watch now runs as an **in-process asyncio task** managed by the FastAPI lifespan (`WatchController` in `src/squire/watch_controller.py`), not a separate Python subprocess. Start/stop/reload are driven by in-memory `asyncio.Event` signals instead of DB-polled `watch_commands` rows, eliminating the ~5-second command-polling latency and the hidden-subprocess-crash failure mode. A new `WatchController.status()` adds a first-class `state` field (`stopped` | `starting` | `running` | `failed`) with a `last_error` message, so a crashed cycle surfaces in the UI instead of leaving the status stuck. Loop crashes no longer take the API down: the supervisor wraps the loop in a top-level `try/except` that flips state to `failed` and finalizes half-open `watch_runs`/`watch_sessions` rows.
- **Auto-start on container boot:** New opt-in `watch_autostart` preference (toggle on the Watch page → Control card) persists in `watch_state`; the lifespan calls `controller.start()` on boot when it's enabled, so watch survives container restarts without a manual click. Defaults to off.
- **Concurrency guard:** A DB-backed holder lock (`watch_state.watch_holder` row with UUID + TTL + periodic heartbeat) protects against two watch loops running against the same SQLite — e.g. an accidental `uvicorn --workers 2` or invoking `squire watch` standalone while the web server already runs watch. The second caller gets `status="holder_busy"` and exits cleanly.
- **Config reload latency:** `PATCH /api/config/*` and `DELETE /api/config/{section}` now invoke `WatchController.reload()` directly (sets an `asyncio.Event`) instead of inserting a row that the subprocess polled for. Effective update arrives at the next cycle boundary, typically sub-millisecond.
- **Graceful shutdown:** `WatchController.stop()` signals shutdown, waits up to 30 s for the in-flight cycle to drain, then cancels the task. Cycle-level timeout (`cycle_timeout_seconds`, default 300 s) remains the first line of defense; worst case the container's existing stale-run cleanup on the next boot handles it.
- **`squire watch` CLI:** The standalone CLI entrypoint still works and remains the path for headless deployments. Internally it now constructs a `WatchController`, shares the same holder lock (so the CLI can't collide with the web UI), and listens for SIGTERM/SIGINT to trigger a clean `controller.stop()`.
- **Long-running memory fix:** `all_cycle_records` is now bounded to the most recent 500 cycles (`_ALL_CYCLES_MAX`). Previously this list grew for the life of a watch run — on a 5-minute interval over months it would accumulate tens of thousands of small dicts. Final watch-completion reports now reflect the bounded window, which is plenty for operator review.

### Removed

- **`watch_commands` SQLite table:** Dropped in a forward-only migration; the subprocess command queue is obsolete. The related helpers `DatabaseService.insert_watch_command`, `get_pending_watch_commands`, and `update_watch_command_status` are removed.
- **`watch_state.pid` row:** Removed on migration. The field was only consulted to check if the subprocess was still alive — superfluous now that the controller is in-process. The `WatchStatusResponse.pid` API field is gone; consumers should read `state` instead.
- **Subprocess liveness probing:** Every `os.kill(int(pid), 0)` call in `src/squire/api/routers/watch.py` is deleted, along with the `_finalize_stale_watch_process` helper. Stale-run cleanup is now a one-shot `finalize_stale_watch_runs_on_boot` run at lifespan startup.

### Migration

- The `watch_commands` table is dropped on first boot via a forward-only migration; the `pid` row in `watch_state` and any stale `watch_holder` row are deleted in the same pass. No manual intervention needed.
- **Breaking**: `WatchStatusResponse.pid` is gone. The first-party UI is updated in lockstep. Third-party consumers of `/api/watch/status` that read `pid` should migrate to `state` (`"stopped" | "starting" | "running" | "failed"`) and `last_error`.
- Operators who ran `squire watch` standalone keep doing so — the CLI command is preserved. If you run the web server *and* `squire watch` against the same `squire.db`, the second to start will now exit immediately with a "holder_busy" message; pick one.

## [0.19.0] — 2026-04-18

### Removed

- **Alert-rule engine:** Removed the in-project threshold-based alert engine — `alert_rules` SQLite table (dropped on first launch via forward-only migration), `GET/POST/PUT/DELETE/POST toggle /api/alerts*` REST endpoints, `create_alert_rule` / `list_alert_rules` / `update_alert_rule` / `delete_alert_rule` LLM tools on the Notifier sub-agent, `squire alerts {list,add,remove,enable,disable}` CLI sub-app, the Notifications page "Alert Rules" tab and form, and the `/alerts` chat slash command. The Notifier sub-agent is kept but trimmed to `send_notification` only. Webhook channels, notification history, approval notifications, and watch-event notifications are unchanged. Alerting is better delegated to external monitoring stacks (Prometheus/Alertmanager, Grafana, Uptime Kuma, Zabbix); a future inbound-alert ingestion endpoint is tracked separately. **Breaking change** for anyone relying on alert rules — export `alert_rules` rows before upgrading if the data is needed (resolves #143).

### Added

- **DB-backed config overrides:** UI edits to `app`, `llm`, `watch`, `guardrails`, `notifications`, and `skills` now persist as rows in a new `config_overrides` SQLite table (auto-created on first boot) and override `squire.toml` at load time. `squire.toml` is user-owned and read-only from the app's perspective. Pydantic config loaders compose a new `DatabaseOverrideSource` between env and TOML, so the precedence is **env vars > DB overrides > `squire.toml` > code defaults** for every mutable section. `DatabaseConfig` deliberately opts out of DB overrides to avoid a chicken-and-egg path resolution loop.
- **Config provenance in API:** `ConfigSectionMeta` now includes a `sources` map (`{field: "env" | "db" | "toml" | "default"}`) so `GET /api/config` reports where each field's effective value came from.
- **Reset endpoints:** `DELETE /api/config/{section}` and `DELETE /api/config/{section}/{field}` clear UI-driven overrides so values revert to TOML/defaults. Both rebuild the in-memory singleton, rewire downstream services (notifier/guardrails/skills), and enqueue a watch reload command.
- **Config UI provenance indicators:** Each config field shows a small database pip when its current value came from a UI override; clicking the pip deletes that single override. A "Reset" button on each section header clears every DB override for that section at once.
- **Watch subprocess deep reload:** A new `reload_config` command (enqueued automatically by any PATCH/DELETE on `/api/config`) rebuilds `WatchConfig`, `GuardrailsConfig`, `NotificationsConfig`, and the `NotificationRouter` from DB + TOML + defaults, closes the old notifier, and re-attaches fresh risk gates to the running agent (handles both single-agent and multi-agent modes). `_interruptible_sleep` now reads its interval through a getter so a mid-sleep reload that shortens `watch.interval_minutes` takes effect before the next cycle fires.

### Changed

- **Configuration UI:** Removed the "Save to disk" checkbox from every config form. UI edits now always go to the DB and live-apply; use the section Reset or per-field pip to revert. The Watch page drawer now PATCHes `/api/config/watch` + `/api/config/guardrails` directly and revalidates SWR caches so reopening the drawer shows fresh values.
- **Prompting strategy overhaul:** Applied the prompting review punch-list across `src/squire/instructions/` and the `safe_tool` decorator. Five changes:
  - **Host attribution via tool envelope (not prose):** `safe_tool` now inspects the wrapped function's signature and prepends `[host=X]\n` to the result when the tool accepts a `host` parameter. The root and sub-agent prompts lost the ~200-token "Host-scoped tools" block that previously taught the model not to mix hosts — the result envelope carries that information mechanically.
  - **Deduplicated shared contract:** A new `build_tool_discipline()` section in `shared.py` carries tool-calling rules (including the anti-hallucination line) once per prompt. Sub-agents received a `build_style_summary()` replacement for the full conversation-style block since the router/root already produces the user-visible voice. Monitor drops the risk-tolerance section entirely (all its tools are level 1 and never trip the gate).
  - **Static-before-dynamic ordering for cache stability:** Every instruction builder composes `static_block` first, then a `dynamic_block` assembled in strict change-frequency order: risk → hosts → snapshot → watch → skill. Keeps prefix hashes stable for provider prompt caching.
  - **Dropped role-name contradictions:** Sub-agents replaced `## Your Role: System Monitor` (etc.) with `## Scope` so the model no longer sees "You are Squire" followed by "You are the Monitor specialist" — reinforces the single-persona guarantee from `CLAUDE.md`.
  - **Router domain table + few-shot examples:** Multi-agent router now enumerates the four specialists and includes a routing example. Admin agent gained a pre-action reasoning scaffold and a worked example. Notifier agent gained two examples demonstrating structured-argument calls.
  - **Positive framing:** Mechanical pass replacing `Do NOT` / `NEVER` with positive instructions throughout.
  - **Bulleted risk contract:** `format_risk_guidance()` now renders a 3-bullet contract instead of a flat sentence, scannable by the model at a glance.
- **Watch-mode prompt:** The autonomous watch addendum now references prior cycle context in conversation history (previously silent) so the agent skips re-reporting stable state across rotations.

### Removed

- **`PUT /api/watch/config`** — UI should use `PATCH /api/config/watch` (and `PATCH /api/config/guardrails` for risk tolerance) instead. The legacy "update_config" watch command is gone; the subprocess only accepts `reload_config`.
- **`WatchConfigUpdate` schema** and the `persist` query parameter on `PATCH /api/config/*` — no longer used now that UI edits flow through DB overrides.

### Changed — Breaking

- **Alert-rule tool signatures:** `create_alert_rule` and `update_alert_rule` now take typed `field: Literal[...]`, `op: Literal[...]`, `value: float` arguments instead of a free-form `condition: str`. The tool schema teaches the LLM through Python types; the Notifier prompt dropped the condition-DSL prose (6 lines). **Any caller that invoked these tools with `condition="cpu_percent > 90"` (external scripts, saved playbooks, pinned prompts) will fail** — migrate to the structured form: `create_alert_rule(name="x", field="cpu_percent", op=">", value=90)`. The internal condition format stored in the SQLite DB is unchanged (`"{field} {op} {value}"`), so existing alert rows and the `evaluate_alerts` parser keep working without migration.

### Migration

- `config_overrides` is created automatically on first boot — no manual migration needed.
- Operators relying on `PUT /api/watch/config` should switch to `PATCH /api/config/watch`. Scripts using `?persist=true` should drop the parameter; edits are now always durable (stored in `squire.db`).
- Treat `squire.db` with the same sensitivity as `squire.toml`: webhook URLs and SMTP passwords edited via the UI now land there in plaintext.
- `squire.toml` can be mounted read-only in Docker.

## [0.18.0] — 2026-04-18

### Added

- **Tool & skill effect classification:** Every tool declares an `EFFECT` (`read` / `write` / `mixed`); multi-action tools declare per-action `EFFECTS`. New `TOOL_EFFECTS` registry and `get_tool_effect()` helper in `squire.tools`. `GET /api/tools` now includes a tool-level `effect` field and per-action `effect` on multi-action tools; `GET /api/skills` includes `effect` (optional frontmatter `metadata.effect`, default `"mixed"`). The Tools and Skills pages render an Effect column with a colored badge and a filter dropdown (read/write/mixed); the Tools page URL-state backs the new filter. Skill form has a matching Effect selector. Bootstrapped watch playbooks (`recover-container-unhealthy`, `triage-disk-pressure`) are seeded as `effect: write`. Effect is UI-only metadata — orthogonal to risk and not consumed by the risk gate, guardrails, or approval today.
- **Dev tooling:** ``scripts/webhook_receiver.py`` and ``make webhook-receiver`` — stdlib HTTP server that logs Squire webhook POSTs (for integration testing); ``squire.example.toml`` documents localhost and ``host.docker.internal`` URLs.
- **Agent instructions:** Shared guidance for host-scoped tools (default `host`, which host tool output describes, consistency across Docker calls, daemon vs remote confusion, anti-retry after repeated identical failures) on the root Squire agent, Monitor, Container, and router; Container agent now includes `docker_ps` for discovery without a Monitor handoff (also on Monitor for read-only observation).
- **Docker errors:** When Docker fails on `local` (missing CLI, unreachable daemon, or socket/connect errors), Docker tool error text appends a short hint about passing `host=` consistently and lists other configured hosts when available.
- **Sessions filter by watch run:** `GET /api/sessions` now accepts an optional `watch_id` query param that joins through `watch_sessions` to restrict results to chat sessions initiated by that watch.
- **Watch Explorer → Sessions handoff:** Watch Explorer now has an "Open in Sessions" button on the selected run that navigates to `/sessions?watch_id=<id>` with a filter chip and clear button on the Sessions page.
- **Shared URL-state hook:** New `useUrlState` / `useUrlStateSet` / `useUrlStateNumber` hooks in `web/src/hooks/use-url-state.ts` that sync component state with URL search params, modeled after the existing Watch Explorer pattern.

### Changed

- **Host reachability UI:** The Hosts page distinguishes enrollment status from live SSH health. Snapshots now carry a `checked_at` ISO timestamp, and the hosts list/detail render a tri-state connectivity badge (reachable / unreachable / unknown) with a "checked Xm ago" tooltip; both views poll every 30s so the label ticks forward without manual refresh. `POST /api/hosts/{name}/verify` returns `checked_at` and updates the snapshot cache on **both** success and failure (failed probes previously left stale "reachable" data in place). `_collect_snapshot` now runs a cheap reachability probe before invoking `system_info` — the SSH backend swallows connection errors and returns stub data, so an offline host previously looked like a healthy one. The "Active" enrollment badge is dropped — presence on the hosts page already implies enrollment, so only the actionable "Pending Key" state is rendered. (#128)
- **Multi-agent tests:** Sub-agent tool uniqueness is asserted per specialist; the same tool may appear on more than one sub-agent when intentionally shared.
- **Chat model dropdown:** Chat header dropdown now auto-sizes to fit the longest available model name (with min/max caps) instead of a hardcoded 20rem width, so long model ids no longer clip and the layout stays stable across selections.
- **UI state preservation:** Config tabs, Notifications tabs, Watch tabs, Tools filters/sort/expanded rows, and Activity filters are now backed by URL search params and survive navigation away and back. The sidebar also remembers the last full URL visited within each top-level section (via sessionStorage), so clicking `Config` after visiting another page returns the user to the same tab (e.g. Guardrails) they left.

### Fixed

- **Multi-action tool deny:** Adding a multi-action tool (e.g. `docker_container`, `systemctl`) to `tools_deny` now blocks every action on that tool. Previously only single-action tools like `docker_ps` were blocked because the risk gate compared the compound action name (`docker_container:inspect`) against a denied set that only contained the bare tool name.
- **Chat skill loop:** WebSocket skill auto-continue no longer runs up to 15 text-only turns when the model stops calling tools; `[SKILL COMPLETE]` is honored from accumulated assistant text even on a final text-only turn.
- **Skill lookup:** `SkillService.get_skill` (and `delete_skill`) now resolve skills by directory slug, case-insensitive directory match, or declared frontmatter `name`, so chat `?skill=` and the API match how skills are listed; WebSocket skill query params are trimmed.
- **Chat skills:** Session state built when the WebSocket opens (including `active_skill`) is now passed as ADK `state_delta` on each `run_async` call. The runner reloads chat sessions from SQLite, so in-memory `session.state.update` alone never applied skill instructions to the model.
- **DB init race:** `DatabaseService._get_conn` now only flips its ready flag once schema creation has fully completed, so concurrent first callers can no longer observe a partially-built database (e.g. a missing `watch_approvals` table) — fixes a flaky `test_approval_denied` failure on Python 3.13 CI.

## [0.17.0] — 2026-04-12

### Added

- **ADK runtime:** Added a shared ADK runtime layer (`Runner` + `SqliteSessionService`) and serializable session-state builders for chat/watch flows
- **Tests:** Added durable ADK runtime coverage (`tests/test_adk_runtime.py`) and new stop/cooldown/escalation regression checks across chat, watch, and risk-gate tests

### Changed

- **Chat sessions:** `POST /api/chat/sessions` now creates durable ADK sessions without temporary in-memory runners, and chat websocket execution now uses the shared SQLite-backed ADK runtime
- **Risk gate state model:** Risk evaluation now derives from JSON-safe session state fields instead of relying on persisted `RiskEvaluator` Python objects
- **Watch runtime:** Watch mode now uses durable ADK sessions and rotates sessions when context event count exceeds `max_context_events` rather than mutating private in-memory ADK storage
- **Stop generation UX:** Chat stop handling now suppresses post-stop stream/tool emissions server-side and honors backend `stopped` completion semantics in the web client
- **Token accounting:** Chat/watch token aggregation now tracks the latest non-null provider usage values from stream events instead of summing every event payload

### Fixed

- **Bootstrap safety:** Replaced module import-time event-loop `run_until_complete` usage in `squire.agent` with safer async initialization that avoids nested-loop failures
- **Approval docs:** Updated approval protocol docs to reflect current async approval execution behavior
- **ADK session storage:** Runtime now uses a dedicated ADK session SQLite file (`*.adk_sessions.db`) instead of reusing the main Squire app DB, avoiding schema conflicts at web/watch startup
- **ADK bootstrap hosts:** `squire.agent` now guarantees managed-host loading even when imported from an already-running event loop
- **Watch context rotation:** `max_context_events` checks now re-fetch session state from ADK session storage before counting events, improving reliability with durable SQLite-backed sessions
- **Session clear/delete parity:** Session API/CLI deletion now purges durable ADK session records alongside SQL conversation rows

## [0.16.0] — 2026-04-12

### Added

- **Token telemetry:** Provider-reported token usage is now captured per assistant response in chat/watch, aggregated per session/watch session, and exposed in watch cycle summaries (`input`, `output`, `total`)
- **Web visibility:** Session History, chat message history, Watch stats, and Watch cycle history now display token usage metrics
- **Watch hierarchy model:** Added persistent `watch_id`, `watch_session_id`, and `cycle_id` entities (`watch_runs`, `watch_sessions`, `watch_cycles`) plus watch/session report storage (`watch_reports`) for unambiguous long-running watch history
- **Investigation APIs:** Added watch timeline and report retrieval endpoints (`/api/watch/timeline`, `/api/watch/reports`, `/api/watch/reports/{report_id}`) and mirrored timeline feed at `/api/events/timeline`
- **Reports hierarchy APIs:** Added run/session/cycle hierarchy endpoints for reports exploration (`/api/watch/runs`, `/api/watch/runs/{watch_id}`, `/api/watch/runs/{watch_id}/sessions`, `/api/watch/runs/{watch_id}/sessions/{watch_session_id}/cycles`)
- **Workbench UI:** Added Investigation Workbench route at `/reports` with timeline cards, tabbed report details (Summary/Evidence/Memory/Recommendations), and deep-link query state for watch/session/cycle/report navigation

### Changed

- **Documentation:** Aligned [Usage Guide](docs/usage.md), [Architecture](docs/architecture.md), [Watch web integration](docs/design/watch-web-integration.md), and [README](README.md) with Watch Explorer, timeline APIs, watch persistence tables, and Activity query parameters
- **Watch clear API:** `DELETE /api/watch/cycles` OpenAPI docs and response message now describe the full watch datastore reset (runs, sessions, cycles, reports, `watch_events`) and note that Activity `events` rows are untouched; Cycle History dialog copy matches
- **Activity chat logging:** `tool_result` and streaming error rows persist at most 500 characters of detail, matching the live WebSocket `tool_result.output` cap
- **Timeline APIs:** Documented when to use `GET /api/watch/timeline` vs `GET /api/events/timeline` (identical data; watch vs Activity entry points)
- **API schemas:** Session/message/watch status and watch cycle payloads now include token usage fields for downstream clients
- **Watch event scoping:** Watch event rows now store `watch_id`, `watch_session_id`, and `cycle_id`; websocket streaming and cycle history queries are now scoped to the active watch run
- **Watch lifecycle:** `squire watch` now creates watch/session/cycle identifiers, persists cycle outcomes into canonical cycle rows, and emits session/watch completion reports for operator-readable summaries
- **Navigation:** Sidebar Monitoring group now includes Reports; Session History and Watch Cycle History include deep links into the workbench
- **Reports UX:** Reports page now defaults to hierarchy-first navigation (Watch Runs -> Sessions -> Cycles), shows explicit `Watch Report` vs `Session Report` labels, and keeps timeline as a secondary mode
- **Routes/navigation:** Watch Explorer now lives at `/watch-explorer`; `/reports` redirects for backward compatibility
- **Activity UX:** Activity now supports explicit time-window presets/custom start, session/watch filters, and clearer live-window labeling
- **Activity drill-down:** Event rows now show context chips and deep links into Chat, Watch, and Watch Explorer
- **Notification event persistence:** Notification router dispatches are now persisted to `events`, so Activity category filters (including watch.* categories) reflect real emitted notifications

### Fixed

- **Token accounting:** Chat and watch now accumulate token usage across multiple ADK events per turn/cycle, and chat persists token-only assistant turns so session totals do not drop tool-only model usage
- **Cycle history ambiguity:** Cycle listings and details no longer rely solely on recycled cycle numbers; watch/session/cycle identity prevents mixed-session cycle views after rotation
- **Duplicate report confusion:** Reports are now grouped and labeled by report level/type so valid watch + session reports no longer look like duplicate artifacts
- **Watch run persistence:** Starting a new watch no longer clears prior watch history; stop/start now appends a fresh watch run instead of overwriting previous runs
- **Activity completeness:** Chat now logs `tool_result` and streaming error events so Activity better reflects real chat behavior
- **Watch stop finalization:** Stopping watch now always finalizes active cycle/session/run artifacts and emits a watch completion report, including stale-PID cleanup paths where the process already exited
- **Watch Explorer report visibility:** Explorer now uses supported report pagination, prefers report-bearing sessions by default, and resolves `chat_session_id` deep links to the correct watch/session context
- **Watch Explorer maintenance:** Added a clear-history action in Watch Explorer to wipe persisted watch runs/sessions/cycles/reports and `watch_events` rows (Activity feed not cleared)
- **Watch Explorer polish:** Repositioned and restyled the clear-history action so the destructive control is visually prominent and less awkward in the layout
- **Watch Explorer consistency:** Updated the clear-history button to match Session History action styling (outline + eraser icon) with compact `Clear` copy
- **Activity filters:** Added missing watch event categories (`watch.action`, `watch.error`, `watch.incident_detected`, `watch.remediation`, `watch.verification`, `watch.escalation`, `watch.digest`) so Activity filtering matches emitted notifications
- **Watch session cycle counts:** Session summaries in Watch Explorer now include live cycle totals while a watch session is still running (instead of remaining at zero until session close)
- **Watch Explorer reports:** Session report picker matches `report_type === "session"` only so future report types do not leak into the session slot
- **Database:** Removed unused `reset_watch_history` helper (clear path is `delete_watch_cycles` only)
## [0.15.0] — 2026-04-11

### Added

- **Watch autonomy:** Added structured watch lifecycle contract (detect → RCA → remediate → verify → escalate), incident/playbook injection, phase and incident event types, cycle outcomes in telemetry, anti-flapping controls (`max_identical_actions_per_cycle`, cooldown windows, remote action cap), and periodic digest notifications
- **Watch analytics:** Persisted cumulative watch metrics in `watch_state` (`total_actions`, `total_blocked`, `total_resolved`, `total_escalated`, `last_outcome`) and exposed richer cycle summaries (`blocked_count`, incident stats, resolved/escalated flags)
- **Tests:** Added `test_watch_autonomy.py` and expanded watch emitter/config coverage for new autonomy and safety behavior
- **Watch playbooks (user-managed):** Added dynamic playbook routing from Skills metadata (`incident_keys` + `hosts`) with deterministic matching, single-match plausibility checks, LLM tie-break for overlaps, semantic fallback for unmatched incidents, and generic fallback on low confidence
- **Skills API/UI:** Added incident family catalog endpoint, router dry-run simulation endpoint, starter playbook bootstrap endpoint, conflict preview UI, and watch-playbook metadata editing (`hosts`, `incident_keys`)
- **Watch telemetry:** Added playbook selection phase events and counters for deterministic/semantic/generic routing paths
- **Web LLM model selection:** Chat header and Configuration > LLM now use provider-backed model dropdowns instead of free-text model entry; chat changes still persist and auto-reconnect the current session

### Changed

- **Watch UI:** Live stream and cycle history now display incident/phase telemetry, blocked counts, and resolved/escalated outcomes; watch config drawer now supports new autonomy safety controls
- **Docs/config:** Updated watch-mode docs and example config to reflect strict-autonomy behavior, corrected `cycles_per_session` default to `12`, and documented new watch config fields and notification categories
- **Skills schema:** Canonicalized skill host targeting to `metadata.hosts` (list) with legacy `metadata.host` retrofit on load; renderer persists only `hosts`

### Fixed

- **Watch safety updates:** Live `update_config` commands now validate incoming values against `WatchConfig` constraints and reject invalid guardrail-disabling values (such as `0` for per-cycle safety limits)
- **Playbook routing resilience:** Added bounded LLM usage for watch/dry-run playbook routing with per-request call caps and per-call timeouts; watch mode also wraps routing in a cycle-safe timeout fallback
- **Skills dry-run safeguards:** `POST /api/skills/playbooks/dry-run` now limits incident batch size and defaults to heuristic routing unless `use_llm=true` is explicitly requested
- **Tests/CI:** Wrapped a long `Incident(...)` constructor call in `test_watch_playbook_router.py` to satisfy Ruff's 120-character line length check and unblock the lint job

## [0.14.1] — 2026-04-11

### Added

- **Docker:** OS packages for common `run_command` diagnostics that `python:*-slim` usually omits (`ping`, `traceroute`, `dig`/`nslookup`, `nc`, `ip`/`ss`, `netstat`, `lsof`, etc.); the image does not install the full default allowlist (for example `docker`, `systemctl`, and `journalctl` remain host- or deployment-specific)
- **Guardrails:** Default `commands_allow` includes `nc` for port reachability checks (operators can remove it for stricter policies)

### Changed

- **Docker / docs:** Clarified that the image adds diagnostic packages, not the entire default `commands_allow`; configuration docs point at `docker/Dockerfile` as the source of truth; `DEBIAN_FRONTEND=noninteractive` set for `apt-get`

## [0.14.0] — 2026-04-11

### Fixed

- **Guardrails:** `run_command` and `read_config` tools now use the live guardrails config instead of a stale module-level cache — runtime changes via the config UI take effect immediately
- **Guardrails:** Chat sessions now use the `deps.guardrails` singleton instead of loading a fresh `GuardrailsConfig()` from disk — non-persisted PATCH changes are respected by new sessions
- **Guardrails:** Per-agent tolerances (`monitor_tolerance`, etc.) are now wired into the risk gate callback via `default_threshold` — previously declared but never consumed
- **Guardrails:** Default `commands_allow` now includes `ls`, `stat`, `file`, `du`, `find`, `grep`, `hostname`, `date`, `whoami`, `id`, `uname`, `mount`, `lsblk`, `top`, `ps`, `which`, `netstat`, `docker`, `systemctl`, `journalctl`, `lsof`, `wc` — fixes `run_command` blocking common read-only commands even at `full-trust` tolerance
- **Web config:** `PATCH /api/config/notifications` now rebuilds `NotificationRouter` (webhook + email) instead of replacing it with a webhook-only dispatcher, so email delivery keeps working after saving notification settings from the UI
- **Watch live config:** `PUT /api/watch/config` now applies all documented watch fields via the `update_config` queue, including numeric risk threshold (updates the running evaluator and session state)
- **Watch API:** `GET /api/watch/config` returns a numeric `risk_tolerance` consistent with effective guardrails/app policy (fixes response validation when watch tolerance was set)
- **Makefile:** `make clean-web` removes `web/out` under `REPO_ROOT` (same as other web targets)

### Changed

- **BREAKING:** `risk_tolerance` and `risk_strict` moved from top-level app config to `[guardrails]` section — env vars change from `SQUIRE_RISK_TOLERANCE` / `SQUIRE_RISK_STRICT` to `SQUIRE_GUARDRAILS_RISK_TOLERANCE` / `SQUIRE_GUARDRAILS_RISK_STRICT`; TOML keys move from top-level to `[guardrails]`

### Added

- **Web config:** Inline help on the Configuration page — section intros, per-field hints, env-override banner, and a page blurb explaining save vs disk vs env vs watch/restart behavior
- **Web config:** `GET/PATCH /api/config/skills` for the skills directory; skills section on the Configuration page; notifications channels editor embedded as a Configuration tab
- **Web config:** Extended PATCH schemas and forms for app name/user id, LLM `api_base`, remaining watch and guardrails fields; watch form pushes changes to a running watch process when status is `running`
- **Web config:** Database tab explains that DB path, snapshot interval, and LLM provider secrets require env/TOML plus process restart
- **Makefile:** `REPO_ROOT`-anchored recipes (`make web`, `web-build`, `ci` targets, etc.) so build and server use this checkout even when Make's working directory differs
- **Web:** `make web` sets `SQUIRE_WEB_STATIC_DIR` to `<repo>/web/out` so the API always serves the bundle that was just built; `_find_static_dir()` falls back to cwd vs package root and picks the newer `index.html` if both exist

## [0.13.0] — 2026-04-11

### Fixed

- **Watch mode:** Fix "unable to stop" from the web UI when the watch process has crashed — `GET /api/watch/status` and `POST /api/watch/stop` now detect dead PIDs and clean up stale `running` state
- **Watch mode:** Fix memory exhaustion caused by unbounded ADK session context growth — sessions now prune old events after each cycle via `max_context_events` (default 40)
- **Watch mode:** Enforce `max_tool_calls_per_cycle` (default 15) which was previously defined but never wired into the watch loop
- **Watch mode:** Free old sessions from `InMemorySessionService` on rotation to prevent abandoned sessions accumulating in memory
- **Watch mode:** Replace the expensive LLM summary call at session rotation with a lightweight last-response carryover — the old approach sent the full bloated context to the model at peak size

### Changed

- **Watch mode:** Lower default `cycles_per_session` from 50 to 12 (rotates every ~1 hour instead of ~4 hours at default interval)
- **Watch mode:** `_run_cycle` now returns `(response_text, tool_count)` tuple for accurate telemetry
- **Watch mode:** Wire `notify_on_action` — dispatches `watch.action` notification when the agent executes tool calls during a cycle
- **Watch mode:** Emit `session_rotated` watch event and report actual `tool_count` in `cycle_end` events (was hardcoded to 0)

### Added

- **Config:** `max_context_events` setting in `[watch]` to control how many ADK session events are kept in context

## [0.12.0] — 2026-04-10

### Added

- **Web chat:** Slash commands (`/`) and `@` mentions with keyboard autocomplete; commands and mentions expand to natural language before send so history matches the model (#73)

## [0.11.0] — 2026-04-09

### Removed

- **Terminal UI (TUI)** — removed the Textual-based interface, the `squire chat` command, and the `textual` dependency. Interactive chat and tool approval are available via the web UI (`squire web`) only.

## [0.10.0] — 2026-04-07

### Added

- **Tools:** Added `docker_volume` and `docker_network` tools to the container agent for listing and inspecting Docker volumes and networks (read-only visibility)

### Security

- Pin runtime and dev dependencies in `pyproject.toml` to exact versions (aligned with `uv.lock`) so installs do not float to newer PyPI releases without an explicit lock update (#65)

### Fixed

- **Tests:** `NotificationsConfig` and `WatchConfig` default tests no longer pick up `~/.config/squire/squire.toml` from the developer machine
- **Docker:** create `/root/.ssh/known_hosts` in the image so SSH to remote hosts works with strict host key checking (#66)

## [0.9.0] — 2026-04-05

### Added

- **Docker:** Multi-stage Dockerfile that builds the Next.js frontend and serves the web UI by default; includes `HEALTHCHECK` directive
- **Docker:** `docker-compose.yml` quickstart with volume, port, and LLM provider configuration
- **API:** `GET /api/health` liveness endpoint returning `{"status": "ok"}`
- **Config:** `SQUIRE_KEYS_DIR` environment variable to override the SSH keys storage directory (default `~/.config/squire/keys/`)

## [0.8.0] — 2026-04-05

### Added

- **Watch:** "Clear History" button on Cycle History tab with confirmation dialog; calls `DELETE /api/watch/cycles` to truncate cycle data (#36)
- **Watch:** "Clear Stream" button on Live Stream tab to clear in-memory event buffer (#36)
- **Watch:** Accumulating "Load More" pagination on Cycle History — cycles append instead of replacing; "Back to Latest" button resets to page 1 (#22)

### Documentation

- **Architecture overview** — new `docs/architecture.md` with Mermaid diagrams covering system overview, agent modes, request flow, risk pipeline, watch loop, tech stack, database schema, and backend registry
- **Usage guide** — new `docs/usage.md` comprehensive guide covering the web UI and CLI, configuration, remote hosts, multi-agent mode, watch mode, alert rules, skills, notifications, and Docker deployment
- **CONTRIBUTING.md** — expand from 54 lines to ~200 lines; add prerequisites, project structure, detailed code conventions, step-by-step tool-authoring guide with accurate registration instructions, testing section with fixture usage, and PR workflow
- **README.md** — restructured as a concise "front door" landing page (~110 lines); detailed content moved to `docs/usage.md`; added documentation hub table linking all docs
- **Configuration reference** — document email notifications (`[notifications.email]`), per-tool risk overrides (`tools_risk_overrides`), host fields (`key_file`, `service_root`), and fix misleading claim about `[[hosts]]` in TOML
- **squire.example.toml** — add `multi_agent`, `tools_risk_overrides`, and `[notifications.email]` sections
- **Tested models** — add model recommendations section with tested Ollama models and cloud provider guidance

### Changed

- **Pattern-based risk analysis** — replaced `PassthroughAnalyzer` with `PatternAnalyzer` from `agent-risk-engine` in the risk evaluation pipeline. Tool call arguments are now inspected for dangerous patterns (e.g., `rm -rf`, `sudo`, SQL drops, sensitive file types) and risk is escalated accordingly. Added homelab-specific custom patterns for privileged containers, firewall modifications, service disablement, Docker data paths, SSH key operations, and crontab changes. (#41)
- **UI color palette** — migrated the web UI from amber/gold to purple primary (#8931c4) + orange accent (#ff7621) palette with matching semantic colors (danger, success, warning, info)
- **docker_compose**: convert flat `RISK_LEVEL=3` to per-action `RISK_LEVELS` dict (ps/config/logs=1, pull=2, restart/up=3, down=4)
- **systemctl**: convert flat `RISK_LEVEL=3` to per-action `RISK_LEVELS` dict (status/is-active/is-enabled=1, start/restart=3, stop=4)
- **Notification tools**: replace broad `except Exception` with specific catches (`sqlite3.IntegrityError`, `ValueError`, `OSError`)
- **system_info**: add `logger.debug()` to silent except blocks for traceability
- **Notification tool docstrings**: improve `delete_alert_rule` and `list_alert_rules` to match project standard

### Fixed

- **Web:** Watch nav item missing from sidebar on initial page load due to hydration mismatch (#35)
- Watch page now defaults to Live Stream tab instead of Cycle History (#37)
- **docker_ps**: add missing `timeout=30.0` to `backend.run()` call to prevent indefinite hangs
- **docker_logs**: remove vestigial `hasattr()` guard — use same direct-call pattern as other tools

## [0.7.0] — 2026-04-05

### Changed

- **Web UI design revamp** — warm palette, display typography, refined components
  - Replaced cold purple primary with warm amber/gold accent across light and dark modes
  - Added Fraunces display serif for headings, paired with Plus Jakarta Sans body
  - Redesigned sidebar with Shield brand icon, animated active indicators, grouped navigation
  - Refined cards (subtle shadows), tables (uppercase headers), dialogs (frosted glass overlay)
  - Chat: warmer message bubbles, staggered welcome animation, tool name accent chips
  - All pages use smooth fade-in-up entrance animations
  - Dynamic version from `importlib.metadata` (replaces hardcoded)

### Added

- **Tools visibility & configuration page** — view all tools with metadata and configure per-tool policies
  - `GET /api/tools` endpoint returns the full tool catalog with name, description, group, parameters, risk levels, and effective guardrails
  - `tools_risk_overrides` field on `GuardrailsConfig` for per-tool (or per-action) risk level overrides
  - Risk gate applies overrides before evaluation — overridden risk levels flow through host/force escalation
  - `/tools` page with table, collapsible multi-action rows, inline risk override inputs, approval policy dropdown, and enable/disable toggle
  - Config changes save through existing `PATCH /api/config/guardrails` with optional persist to `squire.toml`
- **Notifications & alerting overhaul** — alerts actually fire and email notifications are supported
  - Wired `evaluate_alerts()` into the watch loop — alert rules now trigger automatically during watch cycles
  - Email notification channel via SMTP alongside existing webhooks, configured under `[notifications.email]` in `squire.toml`
  - `NotificationRouter` dispatches to all configured channels (webhooks + email); failures in one channel don't block others
  - `update_alert_rule` LLM tool — the Notifier agent can now modify and toggle existing alert rules
  - `POST /api/notifications/test-email` endpoint for verifying email configuration
  - `/notifications` page expanded with three tabs: History (with category filter), Alert Rules (full CRUD), and Channels (webhook + email management)
  - Improved Notifier agent instructions with condition syntax examples and honest capability boundaries
- **Runtime config editing from Web UI** — the `/config` page is now editable instead of read-only
  - `PATCH /api/config/{section}` endpoint for app, llm, watch, guardrails, and notifications sections
  - Per-section editable forms with appropriate input types (selects, switches, tag inputs)
  - Env-var-override detection — locked fields show a lock icon with the env var name
  - Optional persist-to-disk via `?persist=true` query parameter (writes back to `squire.toml` preserving comments)
  - Redacted sentinel values (`••••••`) are automatically preserved during webhook updates
  - Enriched `GET /api/config` response with `env_overrides` per section and `toml_path`
- **Host enrollment system** — Squire generates dedicated SSH keys per host and manages the full lifecycle
  - `squire hosts add` / `remove` / `list` / `verify` CLI commands
  - Web UI host enrollment form with public key display for manual setup
  - `POST /api/hosts`, `DELETE /api/hosts/{name}`, `POST /api/hosts/{name}/verify`, `GET /api/hosts/{name}/public-key` API endpoints
  - `HostStore` service for centralized host management with cascading auth (existing SSH keys → manual fallback)

### Fixed

- **Tool approval no longer causes duplicate prompting** — removed instruction that told the LLM to ask for confirmation before mutations, which conflicted with the risk gate's built-in approval dialog (#46)
- **Tool errors no longer interrupt Squire's chain of thought** — improved risk gate error messages with `[BLOCKED]`/`[DENIED]` prefixes and explicit "do NOT retry" guidance so the LLM acknowledges errors and continues responding (#44)

### Changed

- Notification channel management moved from `/config` to `/notifications` page as the single source of truth
- `deps.notifier` is now a `NotificationRouter` instead of `WebhookDispatcher` (same `dispatch()` interface)
- Risk gate error messages are now structured with `[BLOCKED]`/`[DENIED]` prefixes and include explicit instructions for the LLM to not retry and to inform the user
- Risk tolerance guidance now clarifies that approval happens via UI dialog — the LLM should call tools directly without asking
- All sub-agent instructions updated with consistent error handling guidance ("do NOT stop responding")
- Host configuration moved from TOML `[[hosts]]` to SQLite database — hosts are now added via CLI or web UI with no restart required
- `BackendRegistry` supports runtime `add_host()` / `remove_host()` for hot-reload
- Hosts page shows enrollment status badges and management actions (verify, remove)

### Removed

- TOML `[[hosts]]` configuration support — hosts are now managed exclusively via CLI and web UI

### Documentation

- Updated `README.md` Remote Hosts section to show CLI enrollment commands
- Replaced `[[hosts]]` TOML example in `squire.example.toml` with a pointer to the CLI
- Replaced `docs/configuration.md` Remote Hosts section with full enrollment flow documentation
- Added historical note to `docs/design/multi-machine.md` clarifying that Phase 1 shipped with database-backed enrollment rather than TOML configuration

## [0.6.0] — 2026-04-04

### Added

- **Container lifecycle tools** — three new consolidated tools for full container management:
  - `docker_container` — manage individual containers (inspect, start, stop, restart, remove)
  - `docker_image` — manage images (list, inspect, pull, remove)
  - `docker_cleanup` — prune resources and check disk usage (df, prune_containers, prune_images, prune_volumes, prune_all)
- **Compound action risk evaluation** — risk gate now constructs `tool:action` names for per-action risk levels, enabling fine-grained guardrails configuration (e.g., `tools_deny = ["docker_cleanup:prune_volumes"]`). Also adds `force` flag risk escalation (+1 when `force=True`).
- **Watch mode web integration** — manage and observe watch mode through the web UI at `/watch`.
  - Start/stop watch mode from the browser, with PID-based liveness detection
  - Live streaming of watch cycle activity via WebSocket (tokens, tool calls, tool results, cycle boundaries)
  - Cycle history with expandable event details and paginated browsing
  - Runtime configuration (interval, risk tolerance, check-in prompt) applied without restarting
  - Interactive tool approval when supervising — approval cards with countdown timers appear in the live stream; falls back to auto-deny when nobody is watching
  - Three new SQLite tables (`watch_events`, `watch_commands`, `watch_approvals`) for process-independent IPC
  - Watch process emits granular events and polls for commands between cycles (responsive to stop/config changes)
  - Supervisor connection tracking (`supervisor_count` / `supervisor_connected` in `watch_state`)
- **Skills** (replaces Runbooks) — file-based skill definitions aligned with the [Open Agent Skills spec](https://agentskills.io/specification). Each skill is a `SKILL.md` file with YAML frontmatter + freeform Markdown instructions, stored in a configurable directory (default `~/.local/share/squire/skills`). No database required — skills are version-controllable and editable with any text editor.
  - **SkillService** (`src/squire/skills/`) — file-based CRUD: `list_skills`, `get_skill`, `save_skill`, `delete_skill`. Parses YAML frontmatter with `yaml.safe_load()` and renders back to spec-compliant SKILL.md format (`name`/`description` at top level, Squire-specific fields under `metadata`). Names are validated per the spec (lowercase alphanumeric + hyphens, max 64 chars).
  - **SkillsConfig** (`src/squire/config/skills.py`) — configurable via `[skills]` in `squire.toml` or `SQUIRE_SKILLS_` env vars. Default path: `~/.local/share/squire/skills`.
  - **API** — `GET/POST /api/skills`, `GET/PUT/DELETE /api/skills/{name}`, `POST /api/skills/{name}/toggle`, `POST /api/skills/{name}/execute`. Execute returns skill metadata for the frontend to start a chat session.
  - **CLI** — `squire skills list|show|add|remove|enable|disable`. Create from Markdown file with `--instructions-file`.
  - **Agent integration** — `build_skill_section()` reads `active_skill` from session state and injects freeform instructions into the system prompt. Single `[SKILL COMPLETE]` marker replaces per-step tracking.
  - **Watch mode** — skills with `trigger=watch` are appended to the check-in prompt each cycle.
  - **Web UI** — Skills page (`/skills`) with table listing, create/edit dialog (Markdown textarea for instructions), toggle, delete, and execute (opens in chat). Sidebar updated with Skills link.
- **Clear all sessions** — bulk-delete all chat sessions at once instead of removing them one by one.
  - `DELETE /api/sessions` — new API endpoint; returns `{"deleted": <count>}`.
  - **Web UI** — "Clear All" button (with browser confirmation dialog) on the Sessions page; only shown when sessions exist.
  - **CLI** — `squire sessions clear` command with a `--yes/-y` flag to skip the confirmation prompt. The existing `squire sessions` command is now a sub-command group (`squire sessions list` / `squire sessions clear`).
  - **TUI** — `Ctrl+X` binding opens a confirmation modal and deletes all sessions from the database.
- `DatabaseService.delete_all_sessions()` — deletes all rows from `sessions` and `conversations`, returns the session count.

### Removed

- **Persona customization** — removed `house`, `squire_name`, and `squire_profile` config fields and the three built-in personality profiles (Rook, Cedric, Wynn). Squire now uses a single fixed identity across all interfaces. The `profiles.py` module has been deleted. System prompts, session state, TUI, config files, and documentation have been updated accordingly.
- `**agent-risk-engine` v0.2.0: tool-centric models and state layer** — `ToolDef`, `ToolRegistry`, `ToolAnalyzer`, `SystemState`, `StateMonitor`, `NullStateMonitor`, and `RiskScore.alternative` removed from public API.

### Changed

- `**agent-risk-engine` migrated to PyPI** — replaced local path dependency (`packages/agent-risk-engine/`) with standard PyPI dependency (`agent-risk-engine>=0.2.0`). The `packages/` directory is removed.
- **CI/CD improvements** — split CI into parallel jobs (lint, test, frontend, docker) with dependency caching. Fixed broken Dockerfile (missing `packages/` copy for `agent-risk-engine`). Added `.dockerignore`. Added Dependabot for Python, npm, and GitHub Actions. `make ci` now includes frontend lint and build checks.
- **Release workflow** — pushing a `v*` tag now builds and publishes the Docker image to `ghcr.io/willdah/squire` and creates a GitHub Release with changelog notes.
- `**agent-risk-engine` v0.2.0: action-centric protocol** — breaking refactor repositioning the package as an open protocol with Python reference implementation.
  - `**Action` envelope** — new `Action(kind, name, parameters, risk, metadata)` dataclass replaces the `(tool_name, args, tool_risk)` tuple. `kind` enables per-category routing; `metadata` carries framework-provided context.
  - **3-layer stateless pipeline** — `RuleGate` → `ActionAnalyzer` → `ActionGate`. The `StateMonitor` layer is removed; the engine no longer tracks call history internally. Temporal context (loop detection, session state) is the framework's responsibility and flows in via `Action.metadata`.
  - **Kind-aware routing** — `RuleGate` gains `kind_thresholds` for per-kind threshold overrides. `allowed_tools`/`approve_tools`/`denied_tools` renamed to `allowed`/`approve`/`denied`.
  - **Kind-scoped patterns** — `RiskPattern.kinds` enables patterns that only fire for specific action categories.
  - `**CallTracker` standalone** — extracted from pipeline to standalone utility. `check()` returns `dict` instead of `SystemState`. New configurable `repetition_ratio` parameter.
  - **Renames** — `ToolDef` → `ActionDef`, `ToolRegistry` → `ActionRegistry`, `ToolAnalyzer` → `ActionAnalyzer`.
  - `**PROTOCOL.md`** — new language-agnostic protocol specification defining risk levels, gate results, action envelope, and evaluation semantics.
- **README restructure** — rewrote README with new Interfaces section (Web UI, TUI, CLI), Docker deployment section, Notifications config section, badges, expanded Quickstart and Development sections. Removed stale Personalization TOC entry. Trimmed config duplication in favor of linking to `docs/configuration.md`. Updated `docs/cli.md` with `squire web` command, fixed watch config table to reflect `[guardrails.watch]` restructure, added `Ctrl+X` keyboard shortcut.
- **Runbooks replaced by Skills** — the database-backed runbook system (ordered steps in `runbooks` + `runbook_steps` tables) has been replaced by file-based skills. This simplifies the data model (no numbered steps, no per-step tracking), makes skills version-controllable, and aligns with the Open Agent Skills spec. The `[STEP N COMPLETE]` / `[RUNBOOK COMPLETE]` markers are replaced by a single `[SKILL COMPLETE]` marker. Existing runbook tables in the database are left in place but no longer queried. The WebSocket `?runbook=` query param is now `?skill=`. CLI commands changed from `squire runbooks` to `squire skills`. Added `pyyaml>=6.0` as an explicit dependency (was already a transitive dep).

### Fixed

- **Hide internal ADK tool calls from web UI chat** — `transfer_to_agent` (and any future ADK-internal tools) are no longer streamed to the WebSocket client. Previously, agent routing events appeared as unhelpful `🔧 transfer_to_agent: {'result': None}` messages that exposed internal sub-agent names. `ADK_INTERNAL_TOOLS` is now a public constant in `callbacks/risk_gate.py` shared by both the risk gate and the chat router.

## [0.5.0] — 2026-03-18

### Added

- **Makefile** — standardized development commands (`make install`, `make lint`, `make test`, `make ci`, `make web-dev`, `make docker-build`, `make clean`, etc.). Run `make help` for the full list.
- **CLAUDE.md** — project context file for Claude Code with overview, tech stack, directory structure, commands, code conventions, and CI details.
- **Stop generation** — red stop button appears while the agent is responding, allowing users to cancel mid-stream. Partial responses are preserved in the chat and persisted to the database. Also dismisses any pending approval dialog.

### Fixed

- **Chat input focus** — the message input now retains focus after sending a message and after clicking the "New Chat" button, so users can keep typing without clicking back into the field.

### Changed

- **Consolidated guardrails config** — merged `[security]`, `[risk]`, and watch-mode risk fields into a single `[guardrails]` section. All safety policy (tool overrides, command/path guards, per-agent tolerances, watch-mode risk) now lives in one place. The old `[security]` and `[risk]` TOML sections are removed. Watch-mode risk overrides moved to `[guardrails.watch]` sub-table; `[watch]` now contains only operational settings (interval, timeout, prompt, notifications). Renamed fields: `command_allowlist` → `commands_allow`, `command_denylist` → `commands_block`, `config_allowlist` → `config_paths`, `allow`/`approve`/`deny` → `tools_allow`/`tools_require_approval`/`tools_deny`. Per-agent tolerances moved from top-level to `[guardrails]` with shorter names (e.g., `monitor_risk_tolerance` → `monitor_tolerance`). Env prefix changed from `SQUIRE_SECURITY_`/`SQUIRE_RISK_` to `SQUIRE_GUARDRAILS_`. This is a breaking change — existing `squire.toml` files need to be updated.
- **Sticky chat top bar with icon button** — the chat header (title, connection dot, new chat) now uses `shrink-0 bg-card` so it stays pinned at the top of the flex column during long conversations. Replaced the "New Chat" text link with a `SquarePen` icon button for a cleaner look.
- **Web UI restructure: chat-first identity** — Squire is the brain, not the eyes. Removed dashboard and alert rule CRUD in favor of a chat-first experience that leans on dedicated homelab tools (Beszel, Grafana, Portainer) for metrics and container management.
  - Removed Dashboard page and all dashboard components (stat cards, container grid, trend chart) — for live metrics, use Beszel or Grafana.
  - Root (`/`) now redirects to `/chat` instead of `/dashboard`.
  - Events renamed to **Activity** (`/activity`) — Squire's own tool calls, watch mode actions, and denied requests.
  - Alerts reframed as **Notifications** (`/notifications`) — removed alert rule CRUD form; shows notification category cards (watch events, risk gate denials, webhook destination) and recent notification history. Alert rules are now managed conversationally.
  - Hosts page simplified to a **host registry** — shows name, address, user, services, tags, and reachable/unreachable status. No more live CPU/memory stats or container grids.
  - Sidebar reorganized: Chat, Activity, Sessions | Hosts, Notifications, Config.
  - Removed `use-system-status` hook, `stat-card`, `container-grid`, `trend-chart` components, and `alert-form` component.
- **Web UI modernization** — visual polish pass across the entire web frontend:
  - Typography overhaul — Plus Jakarta Sans for UI text, JetBrains Mono for code/config; semibold tracking-tight headings, relaxed body line-height.
  - Indigo primary accent color (`oklch(0.45 0.24 265)` light / `oklch(0.68 0.2 265)` dark) replaces colorless gray.
  - Blue-purple tint on all neutral OKLCH values for a cool premium feel instead of flat gray.
  - Theme persistence — dark/light choice saved to `localStorage` and applied before first paint (no flash-of-wrong-theme).
  - Skeleton shimmer loading states replace plain text on Dashboard, Hosts, and Config pages.
  - Chat markdown rendering — assistant messages render headings, code blocks, lists, bold, and links via `react-markdown` + `remark-gfm`.
  - Soft streaming indicator — glow border + bouncing dots replace the harsh yellow border and spinner.
  - Welcome empty state in chat with suggestion chips ("Show system status", "Check containers", "List alerts").
  - Connection status shown as colored dot (green/yellow/red) instead of plain text.
  - Theme-aware gauge colors (`--gauge-ok`, `--gauge-warn`, `--gauge-crit`) with gradient progress bars on stat cards.
  - Warm empty states with icons on all pages (containers, events, alerts, sessions).
  - Event timeline with vertical line and colored dots per category.
  - Config viewer renders top-level keys as label + mono value with collapsible raw JSON toggle.
  - Linear-style sidebar active state (`bg-primary/10` + left border) with section labels and version footer.
  - Staggered `animate-fade-in` entrance animations on cards and list items.
  - Mobile nav sheet closes on link click.
  - Session table shows relative time ("2h ago") with full timestamp on hover.
  - Events page wraps filters in a Card with event count badge.

### Fixed

- **Chat response duplication in multi-agent mode** — when a sub-agent's response arrived via the ADK final response event (not as streaming tokens), the full accumulated text from all agents was sent as `message_complete`, causing the previous agent's response to be repeated in a new chat bubble. Two fixes: (1) `response_parts` is now reset after each tool call/result so `message_complete` only contains the current text segment, not prior sub-agents' text; (2) the `is_final_response` handler detects and sends only genuinely new content as a delta token.
- **Approval dialog overflow** — the tool approval modal was too narrow (`max-w-sm`), causing long command arguments and footer buttons to spill outside the dialog. Widened to `max-w-lg` with `whitespace-pre-wrap` and `break-all` on the arguments block.

## [0.4.0] - 2026-03-18

### Added

- **Web interface** (`squire web`) — browser-based frontend for interacting with Squire, powered by a FastAPI backend and Next.js 15 frontend with shadcn/ui components.
- **FastAPI backend** (`src/squire/api/`) — full REST API and WebSocket layer reusing the same backend services as the TUI (DatabaseService, BackendRegistry, WebhookDispatcher, ADK agent runner).
  - `GET /api/system/status` — live system snapshots for all hosts.
  - `GET /api/system/snapshots` — historical snapshots for trend charts.
  - `GET /api/hosts`, `GET /api/hosts/{name}` — host list and detail with current status.
  - `WebSocket /api/chat/ws/{session_id}` — bidirectional streaming chat with tool call indicators and approval flow.
  - `POST /api/chat/sessions` — create new chat sessions.
  - `GET /api/sessions`, `GET /api/sessions/{id}/messages`, `DELETE /api/sessions/{id}` — session history management.
  - `GET/POST/PUT/DELETE /api/alerts` — alert rule CRUD with condition validation.
  - `POST /api/alerts/{name}/toggle` — enable/disable alert rules.
  - `GET /api/events` — filterable event timeline query.
  - `GET /api/config` — current effective configuration (all sections).
  - `GET /api/watch/status` — watch mode state.
- **WebApprovalBridge** — WebSocket-based approval provider that mirrors the TUI's ApprovalBridge for interactive tool approval in the browser.
- **Next.js 15 frontend** (`web/`) — App Router with TypeScript, Tailwind CSS, shadcn/ui components.
  - Dashboard page with CPU/memory/disk gauges, container status grid, and 24h trend charts (Recharts).
  - Chat interface with WebSocket streaming, tool call indicators, and approval dialog modal.
  - Session resume — click a past session to reconnect and continue the conversation.
  - Host overview grid with drill-down to individual host detail pages.
  - Alert rules management — create, edit, toggle, and delete rules from the browser.
  - Event timeline with category filtering and auto-refresh.
  - Session history browser with resume and delete actions.
  - Configuration viewer with tabbed sections (app, LLM, database, security, watch, notifications, risk, hosts).
  - Dark/light theme toggle with system preference detection.
  - Mobile-responsive layout with collapsible sidebar navigation.
- `**squire web` CLI command** — starts the combined API + frontend server (`--port`, `--host`, `--reload` flags). Default port 8420.
- `fastapi` and `uvicorn[standard]` added to project dependencies.
- Background snapshot collection in the web server — periodic system status updates shared across all API consumers.

## [0.3.0] - 2026-03-16

### Fixed

- **LocalBackend crash on missing commands** — `FileNotFoundError`, `PermissionError`, and `OSError` from `create_subprocess_exec` are now caught and returned as `CommandResult` instead of propagating up and breaking the event loop. Fixes macOS crash when the agent calls Linux-only tools like `journalctl`.
- **Chat pane error handling** — agent errors now show a user-friendly message, log the full traceback, persist error details to the database, and guard against `UnboundLocalError` on `session_id`.

### Added

- `**safe_tool` decorator** — defense-in-depth wrapper applied to all ADK tool functions. Catches any uncaught exception and returns it as a string so the LLM can reason about failures instead of crashing. Preserves function metadata for ADK schema discovery.
- **Watch mode error context injection** — when a watch cycle fails, the next cycle's prompt includes the error so the agent can adapt (e.g. skip unavailable tools).

## [0.2.0] - 2026-03-15

### Added

- **Multi-agent architecture** — Squire can now be decomposed into 4 specialized sub-agents (Monitor, Container, Admin, Notifier) using Google ADK's transfer pattern. Enable with `multi_agent = true` in config. The LLM routes requests to the appropriate specialist while maintaining a single unified persona. Each sub-agent has scoped tools and its own risk gate callback. (#1)
- `ApprovalProvider` protocol (`src/squire/approval.py`) — frontend-agnostic interface for tool approval, decoupling the risk gate from the TUI. Includes `DenyAllApproval` for headless modes.
- `create_risk_gate()` factory (`callbacks/risk_gate.py`) — creates before_tool_callbacks with support for interactive (with ApprovalProvider), headless (auto-deny + notify), and scoped (per-agent tool sets) modes.
- Tool groupings (`tools/groups.py`) — `MONITOR_TOOLS`, `CONTAINER_TOOLS`, `ADMIN_TOOLS` with matching risk level dicts for sub-agent scoping.
- Shared instruction helpers (`instructions/shared.py`) — reusable section builders (identity, conversation style, risk, hosts, system state, watch mode addendum) for consistent persona across all agents.
- Notification tool stubs (`tools/notifications/`) — `send_notification`, `list_alert_rules`, `create_alert_rule`, `delete_alert_rule` for the Notifier sub-agent.
- Service registry extensions (`tools/_registry.py`) — `get_db()`/`set_db()` and `get_notifier()`/`set_notifier()` for notification tool dependencies.
- ADK web/CLI entry point (`agent.py`) — exposes `root_agent` for `adk web` and `adk run` discovery. Respects `multi_agent` config. Tools above risk tolerance are auto-denied (no interactive approval in ADK dev server).
- **Autonomous watch mode** (`squire watch`) — headless monitoring loop that periodically injects check-in prompts into the agent. Tools above the watch risk tolerance are denied outright with notifications. Session rotation bounds memory. Configurable via `[watch]` TOML section. (#2)
- `WatchConfig` (`config/watch.py`) — pydantic-settings for watch mode: interval, threshold, tool budget, cycle timeout, session rotation, allow/deny overrides.
- **Alert rule management** — three interfaces for managing alert rules, all backed by SQLite:
  - Agent tools: `create_alert_rule`, `delete_alert_rule`, `list_alert_rules`, `send_notification` (via Notifier sub-agent)
  - CLI: `squire alerts list|add|remove|enable|disable`
  - TUI: read-only `AlertsPanel` showing active rules and status
- `ConditionEvaluator` (`notifications/conditions.py`) — safe `<field> <op> <value>` DSL for alert conditions. No `eval()` — parsed at creation time, evaluated against snapshot fields.
- `alert_evaluator` (`notifications/alert_evaluator.py`) — background evaluator that checks alert rules against snapshots and fires notifications respecting cooldown periods.
- Per-agent risk tolerances — optional `monitor_risk_tolerance`, `container_risk_tolerance`, `admin_risk_tolerance`, `notifier_risk_tolerance` config fields that fall back to the global threshold.

### Changed

- `**risk_tolerance` config uses `RiskTolerance` enum** — replaced untyped `Any` field with a `StrEnum` (`read-only`, `cautious`, `standard`, `full-trust`). Integer and digit-string inputs are coerced via a `BeforeValidator`, so existing TOML and env var values continue to work.
- **Risk gate callback refactored to factory pattern** — `risk_gate_callback` replaced by `create_risk_gate()` which accepts `ApprovalProvider` via closure instead of importing a TUI singleton. Core agent logic no longer imports from `tui/`.
- **Approval bridge singleton removed** — `ApprovalBridge` is now instantiated in `main.py` and injected into the risk gate factory and TUI via constructor parameters.
- **Background snapshots decoupled from TUI** — `_background_snapshots()` accepts an `on_snapshot` callback instead of a TUI reference.
- **Risk gate allowlists ADK internal tools** — `transfer_to_agent` is explicitly allowlisted; unknown tools are denied. Prevents both blocking ADK routing and passing through unrecognized tools.
- **Host info fallback in instructions** — `build_hosts_section` falls back to loading from config when session state is empty (fixes host awareness in `adk web`).

## [0.1.1] - 2026-03-14

### Fixed

- **Startup crash with google-adk 1.27+** — `ReadonlyContext` moved from `google.adk.agents` to `google.adk.agents.readonly_context`; updated import path.

## [0.1.0] - 2026-03-14

### Added

- **Multi-machine management** — Squire can now connect to remote hosts over SSH. Configure hosts in `[[hosts]]` TOML sections and target any tool at a specific machine with the `host` parameter (e.g., `docker_ps(host="media-server")`).
- `SSHBackend` — new `SystemBackend` implementation using `asyncssh` with lazy connections, automatic OS detection, keepalive, and SFTP file writes.
- `BackendRegistry` — central factory that creates and caches backend instances per host. `"local"` always maps to `LocalBackend`; configured remote hosts get an `SSHBackend` on first access.
- `HostConfig` model and `[[hosts]]` TOML configuration for defining remote hosts with name, address, user, port, SSH key, and optional tags.
- Multi-host system snapshots — startup and background snapshots now collect from all configured hosts in parallel, with graceful handling of unreachable hosts.
- Agent host awareness — the system prompt lists available hosts so the LLM can match user intent (e.g., "check the media server") to the correct `host` parameter.
- Risk bump for remote operations — tool calls targeting remote hosts receive a +1 risk level increase (capped at 5).
- Per-host status in the TUI status panel.
- TUI name customization — the header, chat placeholder, message prefixes, and ready message all use the configured squire name (from `squire_name` or `squire_profile`) instead of hardcoded "Squire".
- Google ADK-based agent with LiteLLM for multi-model support.
- Textual TUI with chat pane, status panel, and approval modal.
- 8 system tools: `system_info`, `network_info`, `docker_ps`, `docker_logs`, `docker_compose`, `read_config`, `journalctl`, `run_command`.
- Layered risk evaluation system extracted into standalone `agent-risk-engine` package with zero dependencies. Four-layer pipeline: RuleGate (fully implemented), ToolAnalyzer, StateMonitor, ActionGate (stub interfaces). Integer 1-5 risk levels with threshold aliases (`read-only`, `cautious`, `standard`, `full-trust`). Per-tool overrides via `[risk]` TOML section with `allow`, `approve`, `deny` lists.
- Streaming LLM responses in the TUI — tokens appear as they arrive instead of buffering the full response. Streaming bubbles show a yellow border while in progress. Falls back to buffered display if the provider doesn't support streaming.
- Auto-snapshot on conversation start populates system context.
- Pydantic BaseSettings config with TOML loading and env var overrides.
- `SystemBackend` protocol abstraction with `LocalBackend` implementation.
- SQLite persistence for sessions, messages, snapshots, and events.
- Log viewer panel in the TUI.
- Session resume via `squire chat --resume`.
- Async webhook notifications for tool calls and errors.
- Pre-configured Squire personality profiles: Rook (methodical and cautious), Cedric (bold and direct), Wynn (wise and curious). Select via `squire_profile` config.
- Custom squire naming via `squire_name` config, with "Rook" as the default.
- House identity config (`house`) for personalized agent context.
- **Service-aware auto-resolution** — Docker Compose and systemctl tools auto-resolve service names from the host registry. New `systemctl` tool for managing systemd services.
- **Security hardening** — path traversal protection in `read_config`, input validation in `run_command` and `docker_compose`, and `SecurityConfig` allowlist enforcement.
- CI/CD with GitHub Actions — lint, type-check, and test workflows.
- `py.typed` marker for PEP 561 typed package support.
- Multi-machine architecture design doc (`docs/design/multi-machine.md`).
- Dockerfile for containerized deployment.
- MIT license.

### Changed

- Tools now resolve their backend via a central `BackendRegistry` instead of module-level `LocalBackend()` singletons. This is a transparent internal change — tool signatures gain an optional `host` parameter but behavior is unchanged when omitted.
- Renamed `PathsConfig` → `SecurityConfig` and `[paths]` → `[security]` TOML section — better reflects its role as tool security allow/deny lists. Env prefix changed from `SQUIRE_PATHS`_ to `SQUIRE_SECURITY_`.
- Improved system prompt for conversational intelligence — Squire now matches its response to user intent (greetings get greetings, not system dumps). Reordered prompt sections so behavioral guidance comes before system data. Personality profiles now include conversational hints for greetings.
- Tool calls and results no longer clutter the main chat — they appear only in the activity log.

### Fixed

- **Thinking/reasoning content leak** — Models with built-in reasoning (e.g. Qwen 3.5) no longer display their internal thinking in the chat. Thought parts (`thought=True`) are now filtered from the streaming response.
- **First streaming chunk dropped** — The first text chunk of a streamed response was lost when subsequent chunks arrived, causing the beginning of replies to be cut off. The streaming bubble now seeds its raw text buffer with the initial chunk.
- **Tool denial messages** — when a tool call is denied by the risk gate, the denial reason is now explicit so the LLM relays it to the user instead of silently failing.
- Rich markup rendering errors — tool output containing shell variables (`${…}`) or brackets no longer crashes the chat display. Content is now escaped before rendering.
- Streaming message prefix — `[bold]Squire[/bold]:` no longer appears as literal text during streaming; markup prefix and user content are tracked separately.
- Test isolation — config tests no longer pick up local `squire.toml` file.
- Cross-platform CI — `test_system_info_basic` now patches `platform` so it passes on Linux runners.

