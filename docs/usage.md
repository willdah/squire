# Squire Usage Guide

Squire is an AI-powered homelab monitoring and management agent. This guide covers all three interfaces, configuration, remote hosts, watch mode, alert rules, skills, notifications, and Docker deployment.

For individual command flags, see the [CLI Reference](cli.md). For full configuration options, see the [Configuration Reference](configuration.md).

---

## Interfaces

Squire ships three ways to interact with it.

### Web UI

Start with:

```bash
make web
# or
uv run squire web
```

Opens at **http://localhost:8420**. The web server runs FastAPI with a built-in Next.js frontend — no separate process needed.

Custom port:

```bash
uv run squire web --port 9000
```

The web UI has eight pages:

| Page | What it does |
|---|---|
| **Chat** | WebSocket-streamed conversation with tool call indicators and approval dialogs |
| **Activity** | Timeline of tool calls, watch mode actions, and denied requests |
| **Sessions** | Browse, resume, and delete past conversations |
| **Skills** | Create, edit, toggle, execute, and delete skills with a form-based editor |
| **Watch** | Start/stop watch mode, live-stream cycle activity, interactive tool approval with countdown timers, and runtime config changes |
| **Hosts** | Host registry with reachable/unreachable status, services, and tags |
| **Notifications** | Notification category overview and recent history |
| **Config** | Current effective configuration viewer |

### TUI

Start with:

```bash
make chat
# or
uv run squire chat
```

The terminal interface provides a chat pane, system status panel, activity log, and approval modals for high-risk tool calls. Resume a previous session:

```bash
uv run squire chat --resume <session-id>
```

**Keyboard shortcuts:**

| Key | Action |
|---|---|
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear chat |
| `Ctrl+G` | Toggle activity log |
| `Ctrl+S` | Toggle status panel |
| `Ctrl+X` | Clear all sessions |

### CLI

All management operations work without a running UI:

```bash
squire chat                    # interactive TUI
squire chat --resume <id>      # resume a session
squire web                     # web interface
squire watch                   # autonomous monitoring
squire alerts list             # manage alert rules
squire skills list             # manage skills
squire sessions list           # browse sessions
squire version                 # show version
```

See the [CLI Reference](cli.md) for full option details on every command.

---

## Configuration

### Precedence

Settings are resolved in order (highest priority first):

1. **Environment variables** — prefixed with `SQUIRE_*`
2. **TOML config file** — first found from:
   - `./squire.toml` (project directory)
   - `~/.config/squire/squire.toml` (user config)
   - `/etc/squire/squire.toml` (system-wide)
3. **Built-in defaults**

Copy the annotated example config to get started:

```bash
cp squire.example.toml squire.toml
```

The example file ([`squire.example.toml`](../squire.example.toml)) documents every option with its default.

### LLM Setup

Squire uses LiteLLM under the hood, so any model it supports works. The default assumes Ollama running locally:

```toml
[llm]
model = "ollama_chat/llama3.1:8b"
api_base = "http://localhost:11434"
```

For cloud providers, set the appropriate API key as an environment variable and update the model string:

```toml
# Anthropic
[llm]
model = "anthropic/claude-sonnet-4-20250514"
# export ANTHROPIC_API_KEY=...

# OpenAI
[llm]
model = "openai/gpt-4o"
# export OPENAI_API_KEY=...

# Google Gemini
[llm]
model = "gemini/gemini-2.0-flash"
# export GEMINI_API_KEY=...
```

### Risk Tolerance

Risk tolerance is the main dial for controlling what Squire can do automatically versus what requires your approval.

Every tool has a built-in risk level (1–5). The tolerance setting determines the cutoff:

| Tolerance | Level | Auto-allows | Needs approval |
|---|---|---|---|
| `read-only` | 1 | System info, network info, container listing | Everything else |
| `cautious` | 2 | + log viewing, config reads | Compose, systemctl, commands |
| `standard` | 3 | + compose, systemctl | Arbitrary command execution |
| `full-trust` | 5 | Everything | Nothing |

```toml
risk_tolerance = "cautious"    # default
risk_strict = false            # false = prompt for approval; true = deny outright
```

Set via environment variable:

```bash
export SQUIRE_RISK_TOLERANCE=standard
```

**Fine-grained overrides** live in the `[guardrails]` section — per-tool allow/deny/require-approval, command and path guards, and per-agent tolerances. See [Configuration Reference](configuration.md#guardrails----guardrails) for details.

---

## Remote Hosts

Squire manages remote hosts at runtime — no TOML required. Each host gets a dedicated ed25519 SSH key, generated and deployed automatically on enrollment.

### Enrolling a Host

```bash
squire hosts add --name media-server --address 192.168.1.10 --user will
squire hosts add --name nas --address 192.168.1.20 --user will --port 2222 --tags storage
```

If the host is already reachable with your current SSH credentials, Squire installs its key automatically and marks the host `active`. If not, it prints the public key and tells you where to add it:

```
Add this public key to ~/.ssh/authorized_keys on the remote host:

  ssh-ed25519 AAAA...

Then run: squire hosts verify media-server
```

Keys are stored at `~/.config/squire/keys/`.

### Managing Hosts

```bash
squire hosts list              # show all managed hosts and status
squire hosts verify nas        # retry connectivity check
squire hosts remove old-server # delete host and its SSH key
```

### Using Hosts in Conversation

Once a host is enrolled, just mention it by name. Squire routes tool calls to the right host automatically. Every tool also accepts an explicit `host` parameter if you need to be precise.

> **Note:** Remote tool calls receive a +1 risk bump. For example, `docker_ps` is risk level 1 on local — risk level 2 on a remote host. Plan your `risk_tolerance` setting accordingly.

---

## Multi-Agent Mode

By default Squire runs as a single agent. Enable sub-agent decomposition to route requests to specialised specialists:

```toml
multi_agent = true
```

| Sub-agent | Role | Default risk tolerance | Tools |
|---|---|---|---|
| Monitor | Read-only system observation | `read-only` | `system_info`, `network_info`, `docker_ps`, `journalctl`, `read_config` |
| Container | Docker lifecycle management | `cautious` | `docker_logs`, `docker_compose`, `docker_container`, `docker_image`, `docker_cleanup` |
| Admin | Systemd and command execution | `standard` | `systemctl`, `run_command` |
| Notifier | Alerts and notifications | `read-only` | `send_notification`, `list_alert_rules`, `create_alert_rule`, `delete_alert_rule` |

The LLM routes requests to the appropriate specialist. You always interact with Squire — the sub-agent structure is an implementation detail.

Per-agent tolerances are configurable under `[guardrails]` in `squire.toml`. See [Configuration Reference](configuration.md#per-agent-tolerances).

---

## Autonomous Watch Mode

> [!WARNING]
> Watch mode is **experimental** and can take actions on your system. Start with `tolerance = "read-only"` under `[guardrails.watch]` and confirm your alert rules before enabling any corrective behavior.

Watch mode is a headless monitoring loop. Each cycle it:

1. Collects system snapshots from all configured hosts
2. Evaluates your alert rules against the snapshot data
3. Injects a check-in prompt into the agent
4. Lets the agent reason about system state and optionally take action (within risk limits)
5. Persists the response and dispatches notifications

Tools above the configured risk tolerance are auto-denied — there is no interactive approval in headless mode. Session state rotates after a configurable number of cycles to keep memory bounded.

### Starting Watch Mode

```bash
make watch
# or
uv run squire watch              # start the loop
uv run squire watch status       # check status from another terminal
```

You can also start and supervise watch mode from the web UI (Watch page) with live cycle streaming, cycle history, and interactive tool approval with countdown timers.

### Getting Started with Watch Mode

1. Configure at least one LLM provider (see [LLM Setup](#llm-setup) above)
2. Set a conservative watch risk tolerance:
   ```toml
   [guardrails.watch]
   tolerance = "read-only"
   ```
3. Optionally add alert rules:
   ```bash
   squire alerts add --name "disk-full" --condition "disk_percent > 90" --severity warning
   ```
4. Start watch mode:
   ```bash
   squire watch
   ```
5. Monitor from the web UI: `squire web` → Watch page

### Watch Mode Configuration

Operational settings go in `[watch]`; risk policy goes in `[guardrails.watch]`.

```toml
[watch]
interval_minutes = 5           # minutes between cycles
max_tool_calls_per_cycle = 15  # tool call budget per cycle
cycle_timeout_seconds = 300    # max wall-clock time per cycle
cycles_per_session = 50        # rotate session after N cycles
notify_on_action = true        # notify when corrective action taken
notify_on_blocked = true       # notify when tool call blocked

[guardrails.watch]
tolerance = "read-only"        # start here, loosen as confidence grows
tools_allow = []               # additional tools to auto-allow in watch
tools_deny = []                # additional tools to deny in watch
```

See [Configuration Reference](configuration.md#watch-mode-risk-overrides----guardrailswatch) for the full field listing.

---

## Alert Rules

Alert rules trigger notifications when system metrics cross thresholds. Watch mode evaluates them each cycle.

### Managing Rules

```bash
squire alerts add --name "disk-full" --condition "disk_percent > 90" --severity warning
squire alerts add --name "high-cpu" --condition "cpu_percent > 85" --host all
squire alerts add --name "mem-critical" --condition "memory_percent > 95" --severity critical --cooldown 60
squire alerts list
squire alerts disable disk-full
squire alerts enable disk-full
squire alerts remove high-cpu
```

Or just ask Squire: "alert me if disk usage exceeds 90%".

### Condition Syntax

Conditions follow the format `<field> <op> <value>`:

- **field** — snapshot field name (see table below)
- **op** — `>`, `<`, `>=`, `<=`, `==`, `!=`
- **value** — number or string literal

Examples:
```
cpu_percent > 90
memory_used_mb >= 14000
disk_percent > 85
load_5m > 4.0
```

The condition evaluator is safe — no `eval()`, just a structured parser.

### Snapshot Fields

| Field | Type | Description |
|---|---|---|
| `cpu_percent` | float | CPU usage percentage |
| `memory_used_mb` | float | Memory usage in MB |
| `memory_percent` | float | Memory usage percentage |
| `disk_percent` | float | Disk usage percentage |
| `disk_used_gb` | float | Disk usage in GB |
| `load_1m` | float | 1-minute load average |
| `load_5m` | float | 5-minute load average |
| `load_15m` | float | 15-minute load average |
| `uptime_hours` | float | System uptime in hours |

Dot-path notation works for nested fields (e.g., `containers.nginx.state`).

---

## Skills

Skills are file-based instruction sets following the [Open Agent Skills](https://openagentskills.dev) spec. Each skill is a directory containing a `SKILL.md` file with YAML frontmatter.

### Directory Layout

```
~/.local/share/squire/skills/
  restart-on-error/
    SKILL.md
  nightly-cleanup/
    SKILL.md
```

### SKILL.md Format

```yaml
---
name: restart-on-error
description: Check container health and restart errored containers.
metadata:
  host: prod-apps-01
  trigger: manual
---

Check the status of all Docker containers on the target host.
If any containers are in an errored state, check their logs for
the root cause and restart them.
Verify the containers come back healthy after restart.
```

`name` and `description` are required by the spec. Names must be lowercase letters, numbers, and hyphens (max 64 chars). Squire-specific fields (`host`, `trigger`, `enabled`) live under `metadata`.

### Triggers

| Trigger | When it runs |
|---|---|
| `manual` | On demand — from the web UI, CLI, or API |
| `watch` | Appended to the check-in prompt each watch mode cycle |

Here is a watch-triggered example:

```yaml
---
name: nightly-cleanup
description: Clean up unused Docker images and volumes nightly.
metadata:
  host: all
  trigger: watch
---

Check for unused Docker images older than 7 days and dangling volumes.
Remove them to free disk space. Report what was cleaned up.
```

Executing a manual skill opens a new chat session with the instructions pre-loaded.

### CLI Management

```bash
squire skills list
squire skills show restart-on-error
squire skills add --name my-skill --description "What this skill does" --instructions-file instructions.md
squire skills add --name nightly-cleanup --description "Clean images" --instructions-file cleanup.md --trigger watch
squire skills enable my-skill
squire skills disable my-skill
squire skills remove my-skill
```

The web UI Skills page provides full management with a form-based editor.

The skills directory is configurable via `[skills]` in `squire.toml` (default `~/.local/share/squire/skills`).

---

## Notifications

Watch mode dispatches notifications for alerts, blocked tool calls, and corrective actions. Squire supports webhooks (Discord, ntfy, any HTTP endpoint) and email.

### Webhooks

```toml
[notifications]
enabled = true

[[notifications.webhooks]]
name = "discord"
url = "https://discord.com/api/webhooks/..."
events = ["watch.alert", "watch.blocked", "watch.error"]

[[notifications.webhooks]]
name = "ntfy"
url = "https://ntfy.sh/squire-alerts"
events = ["*"]
```

### Email

```toml
[notifications.email]
enabled = true
smtp_host = "smtp.gmail.com"
smtp_port = 587
use_tls = true
smtp_user = "you@gmail.com"
smtp_password = "app-password"
from_address = "squire@yourdomain.com"
to_addresses = ["admin@yourdomain.com"]
events = ["watch.alert", "watch.error"]
```

### Event Categories

| Event | Description |
|---|---|
| `watch.start` | Watch mode started |
| `watch.stop` | Watch mode stopped |
| `watch.action` | Agent took a corrective action |
| `watch.blocked` | Tool call denied by risk policy |
| `watch.alert` | Alert rule triggered |
| `watch.error` | Exception during a cycle |

Use `"*"` to subscribe to all events. See [Configuration Reference](configuration.md#notifications----notifications) for full options including custom headers.

---

## Docker Deployment

```bash
make docker-build              # build the image
make docker-run                # run with default settings
```

Or manually:

```bash
docker build -f docker/Dockerfile -t squire .

docker run -v squire-data:/data \
  -e SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b \
  -e SQUIRE_LLM_API_BASE=http://host.docker.internal:11434 \
  squire chat
```

The container stores the SQLite database at `/data` — mount a named volume for persistence. The entrypoint is `squire`, so any command works:

```bash
docker run -v squire-data:/data squire watch
docker run -v squire-data:/data squire web
docker run -v squire-data:/data squire alerts list
```

All configuration can be passed via `SQUIRE_*` environment variables or by mounting a config file at `/app/squire.toml`.
