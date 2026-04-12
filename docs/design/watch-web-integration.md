# Watch Mode Web Integration

## Context

Watch mode is Squire's autonomous monitoring loop — it runs headless, collecting system snapshots and sending check-in prompts to the agent on a configurable interval. It can be started from the CLI (`squire watch`) or spawned by the web API (`POST /api/watch/start`). State and telemetry live in SQLite so the web UI, Activity feed, and headless process all see the same truth.

Operators use the **Watch** page for live supervision (stream, scoped cycle list, config). **Watch Explorer** at `/watch-explorer` (the `/reports` path redirects there) is the home for hierarchy-first history: watch runs, sessions within a run, cycles, and completion reports, with query parameters for deep links from Activity and Sessions.

## Architecture

### Process Model

Watch stays as a **separate OS process**, independent of the web server. Communication happens through **SQLite** — the web API writes commands, the watch process writes rows, and both read shared state. This preserves watch mode's ability to run standalone (no web server required).

### Persistence

**Identifiers:** Each invocation gets a `watch_id`. Within it, the agent uses `watch_session_id` rows tied to the ADK `adk_session_id` (chat session id). Each check-in cycle has a stable `cycle_id`. These keys scope `watch_events`, cycle listings, and the live WebSocket tail.

**`watch_events`** — append-only stream emitted during cycles:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | Monotonic ID for tailing |
| `cycle` | INTEGER NOT NULL | Cycle number within the current session (display) |
| `cycle_id` | TEXT | Stable cycle identifier (joins to `watch_cycles`) |
| `watch_id` | TEXT | Owning watch run |
| `watch_session_id` | TEXT | Owning watch session |
| `type` | TEXT NOT NULL | Event type (see below) |
| `content` | TEXT | JSON payload, varies by type |
| `created_at` | TEXT NOT NULL | ISO 8601 timestamp |

Common event types include `cycle_start`, `cycle_end`, `token`, `tool_call`, `tool_result`, `approval_request`, `approval_resolved`, `error`, `session_rotated`, `phase`, and `incident`.

**`watch_runs`**, **`watch_sessions`**, **`watch_cycles`**, **`watch_reports`** — structured history and operator-facing completion digests (see [architecture.md](../architecture.md#database-schema) for a concise map).

**`watch_commands`** — control messages from web API to watch process:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | Order of commands |
| `command` | TEXT NOT NULL | `start`, `stop`, `update_config` |
| `payload` | TEXT | JSON config overrides for `update_config` |
| `status` | TEXT NOT NULL DEFAULT 'pending' | `pending`, `acknowledged`, `completed`, `failed` |
| `error` | TEXT | Error message if failed |
| `created_at` | TEXT NOT NULL | ISO 8601 timestamp |

**`watch_approvals`** — when the headless pipeline surfaces an approval-shaped request, rows correlate with `approval_request` / `approval_resolved` events:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | Order |
| `request_id` | TEXT UNIQUE NOT NULL | Correlates with `approval_request` event |
| `tool_name` | TEXT NOT NULL | Tool requesting approval |
| `args` | TEXT | JSON tool arguments |
| `risk_level` | INTEGER NOT NULL | 1–5 |
| `status` | TEXT NOT NULL DEFAULT 'pending' | `pending`, `approved`, `denied`, `expired` |
| `responded_at` | TEXT | When user responded |
| `created_at` | TEXT NOT NULL | ISO 8601 timestamp |

The **`watch_state`** key-value table holds live status (PID, interval, current `watch_id` / `watch_session_id` / `cycle_id`, supervisor connection counts, cumulative autonomy counters, token totals, etc.).

### Event Retention

`cleanup_watch_data` retains the most recent cycles (default cap: 500) and deletes older `watch_cycles` / associated `watch_events` rows; `watch_commands` and `watch_approvals` are also trimmed to bounded row counts. This is separate from **`DELETE /api/watch/cycles`**, which clears the entire watch datastore (runs, sessions, cycles, reports, `watch_events`) while leaving the Activity `events` table intact.

## Watch Process Behavior

### Event Emission

`WatchEventEmitter` wraps `DatabaseService` with typed emit methods. The watch loop streams ADK output and records phase/incident telemetry alongside tool and token events. Emission is best-effort — failures are logged and do not block the cycle.

File: `src/squire/watch_emitter.py`, `src/squire/watch.py`

### Command Polling

The watch process polls `watch_commands` for `pending` rows (including between sleep intervals) so **stop** and **update_config** stay responsive.

- **`stop`** → graceful shutdown path  
- **`update_config`** → applies JSON overrides to in-memory config; effective next cycle  
- **`start`** → acknowledged when the process starts (the web server spawns the process)

### Start Flow

`POST /api/watch/start`:

1. If `watch_state` shows running and `os.kill(pid, 0)` succeeds → returns "already running"
2. If PID is stale → finalizes orphaned run/session/cycle artifacts, then proceeds
3. Inserts a `start` command and spawns `python -m squire watch` detached
4. Returns immediately; clients poll `GET /api/watch/status`

### Strict-Autonomy Gate

Watch mode uses a strict headless risk policy. High-risk work is blocked or deduplicated rather than blocking the loop on interactive approval; telemetry and notifications carry the outcome.

Files: `src/squire/watch.py`, `src/squire/callbacks/risk_gate.py`

## Backend API

### Watch router (`/api/watch`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/watch/status` | Current watch state; corrects stale `running` if the PID is gone |
| `POST` | `/api/watch/start` | Spawn watch if needed |
| `POST` | `/api/watch/stop` | Queue stop; finalizes immediately if process already exited |
| `GET` | `/api/watch/config` | Effective watch settings + numeric watch risk tolerance |
| `PUT` | `/api/watch/config` | Queue `update_config` with partial payload |
| `GET` | `/api/watch/cycles` | Paginated cycles; optional `watch_id`, `watch_session_id` |
| `DELETE` | `/api/watch/cycles` | Full watch datastore reset (not Activity `events`) |
| `GET` | `/api/watch/cycles/{cycle_id}` | Event stream for a cycle; accepts numeric or string `cycle_id`; optional `watch_id` |
| `GET` | `/api/watch/timeline` | Paginated merged timeline (cycles + report markers) for Explorer / Activity |
| `GET` | `/api/watch/reports` | Paginated reports |
| `GET` | `/api/watch/reports/{report_id}` | One report by id |
| `GET` | `/api/watch/reports/watch/{watch_id}` | Latest watch-completion report for a run |
| `GET` | `/api/watch/reports/session/{watch_session_id}` | Latest session report (`watch_id` query required) |
| `GET` | `/api/watch/runs` | Paginated watch runs |
| `GET` | `/api/watch/runs/{watch_id}` | One run summary |
| `GET` | `/api/watch/runs/{watch_id}/sessions` | Sessions in a run |
| `GET` | `/api/watch/runs/{watch_id}/sessions/{watch_session_id}/cycles` | Cycles in a session |
| `GET` | `/api/watch/sessions/by-adk/{adk_session_id}` | Resolve watch session from chat session id |
| `POST` | `/api/watch/approve/{request_id}` | Approve or deny a pending approval row |

### Activity / events router

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/events` | Activity rows; query params include `since`, `category`, `session_id`, `watch_id`, `limit` (default window: last 24 hours if `since` omitted) |
| `GET` | `/api/events/timeline` | Same payload as `GET /api/watch/timeline` — use this path when building Activity-centric or cross-surface deep links |

### WebSocket

`WS /api/watch/ws` — live watch event stream.

**On connect:**

- Increments `supervisor_count`, sets `supervisor_connected` when count > 0
- Replays the current cycle's `watch_events` (by `cycle_id` or legacy numeric cycle), then tails new rows every ~200ms
- New events are filtered to the **active `watch_id`** so reconnects do not mix runs

**Payload:** Each message is the JSON row from `watch_events` (including `type` and `content`).

**On disconnect:** Decrements supervisor count; `supervisor_connected` false when count reaches zero.

File: `src/squire/api/routers/watch.py`

## Frontend

### `/watch` (Watch page)

- Status and stats cards; start/stop; configuration drawer (`PUT /api/watch/config`)
- Live stream tab: WebSocket to `/api/watch/ws`
- Cycle history tab: `GET /api/watch/cycles` with optional `watch_id` / `watch_session_id`, load-more pagination, expandable detail via `GET /api/watch/cycles/{cycle_id}`, links into Watch Explorer

### `/watch-explorer` (Watch Explorer)

- Default **hierarchy** navigation: runs → sessions → cycles; report pickers and tabbed report JSON views
- Optional **timeline** mode and query-driven state: `watch_id`, `watch_session_id`, `cycle_id`, `report_id`, `chat_session_id` (resolved through `GET /api/watch/sessions/by-adk/...`)
- **Clear history** uses `DELETE /api/watch/cycles` (destructive; Activity untouched)

Files: `web/src/app/watch/page.tsx`, `web/src/app/watch-explorer/page.tsx`, `web/src/components/watch/*.tsx`

### Data fetching patterns

- SWR for REST; polling intervals on status-heavy views
- Timeline: `GET /api/watch/timeline` or `GET /api/events/timeline` (identical data; pick route by surface)

## Verification

1. **Start/stop via web UI** — Status transitions; stale PID cleanup if you kill the watch process manually  
2. **Live stream** — Tokens, tools, cycle boundaries on `/watch`  
3. **Cycle history** — Pagination, expand detail, token columns when present  
4. **Watch Explorer** — Hierarchy selection, report tabs, deep link from Sessions or Activity  
5. **Configuration** — Drawer apply; changes on next cycle  
6. **Strict-autonomy** — Low tolerance blocks tools; watch continues; Activity shows `watch.blocked` / related categories  
7. **Headless** — `squire watch` without the web server still writes SQLite; UI catches up when online  
8. **WebSocket reconnect** — Initial burst catches up for the current `watch_id`  
9. **Clear history** — Watch datastore empty; Activity rows remain  
