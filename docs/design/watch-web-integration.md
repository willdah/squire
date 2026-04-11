# Watch Mode Web Integration

## Context

Watch mode is Squire's autonomous monitoring loop — it runs headless, collecting system snapshots and sending check-in prompts to the agent on a configurable interval. Today it's started via CLI (`squire watch`), outputs to stdout logs, and persists state to SQLite. The web UI has a minimal read-only status endpoint but no meaningful integration.

Users need to manage and observe watch mode through the web UI: start/stop the process, see live agent activity as cycles run,
review historical cycles, adjust configuration on the fly, and monitor autonomy outcomes (incident detection, RCA, remediation,
verification, escalation).

## Architecture

### Process Model

Watch stays as a **separate OS process**, independent of the web server. Communication happens entirely through **SQLite** — the web API writes commands, the watch process writes events, and both read shared state. This preserves watch mode's ability to run standalone (headless, no web server required).

### IPC via SQLite

Three new tables support the bridge:

**`watch_events`** — granular event stream emitted by the watch process:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | Monotonic ID for tailing |
| `cycle` | INTEGER NOT NULL | Watch cycle number |
| `type` | TEXT NOT NULL | Event type (see below) |
| `content` | TEXT | JSON payload, varies by type |
| `created_at` | TEXT NOT NULL | ISO 8601 timestamp |

Event types: `cycle_start`, `cycle_end`, `token`, `tool_call`, `tool_result`, `approval_request`, `approval_resolved`, `error`, `session_rotated`.

**`watch_commands`** — control messages from web API to watch process:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | Order of commands |
| `command` | TEXT NOT NULL | `start`, `stop`, `update_config` |
| `payload` | TEXT | JSON config overrides for `update_config` |
| `status` | TEXT NOT NULL DEFAULT 'pending' | `pending`, `acknowledged`, `completed`, `failed` |
| `error` | TEXT | Error message if failed |
| `created_at` | TEXT NOT NULL | ISO 8601 timestamp |

**`watch_approvals`** — interactive approval bridge:

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

The existing `watch_state` key-value table is unchanged.

### Event Retention

Events are cleaned up periodically — retain the last 24 hours or 500 cycles (whichever is greater). Cleanup runs at watch startup and every N cycles. Commands and approvals follow the same retention.

## Watch Process Changes

### Event Emission

A `WatchEventEmitter` class wraps `DatabaseService` with typed methods: `emit_cycle_start()`, `emit_token()`, `emit_tool_call()`, `emit_tool_result()`, `emit_cycle_end()`, etc. The existing `_run_cycle()` method streams ADK events and collects text — it gains event emission calls alongside its existing logic. Emission is fire-and-forget; failures are logged but never block the cycle.

File: `src/squire/watch.py`

### Command Polling

At the top of each loop iteration (before snapshot collection), the watch process queries `watch_commands` for rows with `status='pending'`, ordered by `id`. Processing:

- **`stop`** → sets the `shutdown` asyncio.Event (existing graceful shutdown path)
- **`update_config`** → applies JSON overrides to the in-memory `WatchConfig` (interval, risk tolerance, check-in prompt). Takes effect next cycle. Marks command as `completed`.
- **`start`** → acknowledged on startup (the web server handles actually spawning the process)

Also polls between cycle sleep intervals (not just at cycle boundaries) so that stop commands are responsive even during long intervals. This is done by replacing the single `asyncio.wait_for(shutdown.wait(), timeout=interval)` with a loop that sleeps in shorter increments (e.g., 5s) and checks for commands between sleeps.

### Start Flow

The web API's `POST /api/watch/start` endpoint:
1. Checks if watch is already running (via `watch_state` PID + os.kill(pid, 0))
2. Writes a `start` command to `watch_commands`
3. Spawns `squire watch` as a detached subprocess
4. Returns immediately — frontend polls status until it transitions to "running"

### Strict-Autonomy Gate

Watch mode runs with strict headless risk policy (`strict=True`, `headless=True`) and never waits for interactive approvals.
Supervisor connections in the web UI provide observability only. High-risk actions are denied, deduplicated, and surfaced as
autonomy telemetry and notifications.

File: `src/squire/watch.py`, `src/squire/callbacks/risk_gate.py`

## Backend API

All endpoints under the existing `/api/watch` router.

### REST Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/watch/status` | Current watch state (existing, extended with richer stats) |
| `POST` | `/api/watch/start` | Spawn watch process if not running |
| `POST` | `/api/watch/stop` | Write stop command |
| `GET` | `/api/watch/config` | Current watch + guardrails config |
| `PUT` | `/api/watch/config` | Write `update_config` command with overrides |
| `GET` | `/api/watch/cycles` | Paginated cycle list (aggregated from events) |
| `GET` | `/api/watch/cycles/{cycle}` | Full event stream for a cycle |
| `POST` | `/api/watch/approve/{request_id}` | Approve or deny a pending approval |

### WebSocket Endpoint

`WS /api/watch/ws` — live watch event stream.

**On connect:**
- Increments `supervisor_count` in `watch_state` (integer, starts at 0)
- Sets `supervisor_connected=true` in `watch_state` (derived: count > 0)
- Begins tailing `watch_events` where `id > last_seen_id` at ~200ms poll interval
- Sends initial burst of recent events from the current cycle (so you don't join a blank screen mid-cycle)

**Event forwarding:**
- Each new `watch_events` row is serialized as a WebSocket JSON message
- Message types mirror the chat WebSocket where applicable: `token`, `tool_call`, `tool_result`, `approval_request`, plus watch-specific: `cycle_start`, `cycle_end`, `status_changed`

**On disconnect:**
- Decrements `supervisor_count` in `watch_state`
- Sets `supervisor_connected=false` only when count reaches 0

**Multiple connections:**
- All see the same event stream
- Any connection can respond to approvals (first response wins, others get an "already resolved" message)

File: `src/squire/api/routers/watch.py`

## Frontend

### New Page: `/watch`

A dedicated top-level page in the sidebar navigation.

### Layout: Dashboard + Stream Split

**Top section — Status Card + Stats Card (side by side):**

Status card:
- Watch status badge: Running (green) / Stopped (gray)
- Current cycle number, interval, next-cycle countdown, risk tolerance, PID
- Action buttons: Start/Stop (contextual) and Configure

Stats card:
- Uptime, total tools called, actions taken, tools blocked, errors, session rotation count

**Bottom section — Tabbed view:**

- **Live Stream tab** (default when running): Real-time scrolling log of the current cycle. Shows tool calls with truncated results, streaming agent response tokens, and inline approval cards. Auto-scrolls to bottom. When watch is stopped, shows a placeholder message.
- **Cycle History tab** (default when stopped): Paginated accordion list of past cycles. Each row shows cycle number, timestamp, tool count, status indicator (OK/blocked/error), and duration. Click to expand and see the full event stream and agent response for that cycle. "Load more" pagination at the bottom.

### Configuration Drawer

A right-side sheet/drawer triggered by the "Configure" button. Fields:
- **Interval** — number input (minutes)
- **Risk tolerance** — segmented control (1: Read-only → 5: Full trust)
- **Check-in prompt** — textarea

"Apply" sends `PUT /api/watch/config`. "Cancel" closes without changes. Footer note: "Changes take effect next cycle."

### Approval Flow

When an `approval_request` event arrives on the WebSocket:
- An inline card appears in the live stream with: warning icon, tool name, host, args (in a code block), risk level badge, countdown timer (60s)
- Approve / Deny buttons send `POST /api/watch/approve/{request_id}`
- On resolution, the card updates to show the outcome and the stream continues

Reuses the existing `ApprovalDialog` component pattern from the chat page, adapted for inline stream display.

### Data Fetching

- **Status and config**: SWR with polling (every 5s when stopped, every 2s when running)
- **Live stream**: WebSocket via the existing `useWebSocket` hook, connected to `/api/watch/ws`
- **Cycle history**: SWR with pagination (`/api/watch/cycles?page=N&per_page=20`)
- **Cycle detail**: Fetched on expand (`/api/watch/cycles/{cycle}`)

### Components

| Component | Purpose |
|-----------|---------|
| `WatchStatusCard` | Status badge, cycle info, action buttons |
| `WatchStatsCard` | Session statistics |
| `WatchLiveStream` | Real-time event log with auto-scroll |
| `WatchCycleHistory` | Accordion list of past cycles |
| `WatchCycleDetail` | Expanded view of a single cycle's events |
| `WatchConfigDrawer` | Configuration sheet |
| `WatchApprovalCard` | Inline approval prompt in stream |

Files: `web/src/app/watch/page.tsx`, `web/src/components/watch/*.tsx`

## Verification

1. **Start/stop via web UI**: Start watch from the web UI when stopped, verify process spawns and status transitions to "running". Stop it, verify graceful shutdown.
2. **Live streaming**: With watch running, open `/watch` and verify tokens, tool calls, and cycle boundaries stream in real-time (~200ms latency).
3. **Cycle history**: After several cycles, switch to History tab and verify cycles are listed with correct stats. Expand a cycle and verify full event stream is shown.
4. **Configuration**: Open config drawer, change interval to 1 minute, apply. Verify next cycle runs after ~1 minute instead of default 5.
5. **Strict-autonomy blocking**: Set risk tolerance low enough that a tool is blocked. Verify watch continues with fallback/escalation
   and emits `watch.blocked` / `watch.escalation` telemetry without waiting for approval.
6. **Headless fallback**: Stop the web server, run `squire watch` from CLI. Verify it still works independently — events are written to DB, strict risk gate auto-denies, no errors about missing web server.
7. **Reconnection**: Disconnect and reconnect the WebSocket mid-cycle. Verify the stream catches up (initial burst of current cycle events).
8. **Concurrent viewers**: Open `/watch` in two browser tabs. Verify both see the stream. Submit an approval from one tab, verify the other shows it as resolved.
