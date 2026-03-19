# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **`squire web` CLI command** — starts the combined API + frontend server (`--port`, `--host`, `--reload` flags). Default port 8420.
- `fastapi` and `uvicorn[standard]` added to project dependencies.
- Background snapshot collection in the web server — periodic system status updates shared across all API consumers.

## [0.3.0] - 2026-03-16

### Fixed

- **LocalBackend crash on missing commands** — `FileNotFoundError`, `PermissionError`, and `OSError` from `create_subprocess_exec` are now caught and returned as `CommandResult` instead of propagating up and breaking the event loop. Fixes macOS crash when the agent calls Linux-only tools like `journalctl`.
- **Chat pane error handling** — agent errors now show a user-friendly message, log the full traceback, persist error details to the database, and guard against `UnboundLocalError` on `session_id`.

### Added

- **`safe_tool` decorator** — defense-in-depth wrapper applied to all ADK tool functions. Catches any uncaught exception and returns it as a string so the LLM can reason about failures instead of crashing. Preserves function metadata for ADK schema discovery.
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

- **`risk_tolerance` config uses `RiskTolerance` enum** — replaced untyped `Any` field with a `StrEnum` (`read-only`, `cautious`, `standard`, `full-trust`). Integer and digit-string inputs are coerced via a `BeforeValidator`, so existing TOML and env var values continue to work.
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
- Renamed `PathsConfig` → `SecurityConfig` and `[paths]` → `[security]` TOML section — better reflects its role as tool security allow/deny lists. Env prefix changed from `SQUIRE_PATHS_` to `SQUIRE_SECURITY_`.
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
