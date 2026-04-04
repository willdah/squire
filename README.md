<div align="center">
  <h1>Squire</h1>
  <img src="docs/assets/squire_logo_wide.png" alt="Squire" width="100%">
  <p><strong>Your homelab's faithful attendant.</strong></p>

  [![CI](https://github.com/willdah/squire/actions/workflows/ci.yml/badge.svg)](https://github.com/willdah/squire/actions/workflows/ci.yml)
  [![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
</div>

---

- [Features](#features)
- [Quickstart](#quickstart)
- [Interfaces](#interfaces)
  - [Web UI](#web-ui)
  - [TUI](#tui)
  - [CLI](#cli)
- [Configuration](#configuration)
  - [LLM Setup](#llm-setup)
  - [Risk Tolerance](#risk-tolerance)
  - [Remote Hosts](#remote-hosts)
- [Multi-Agent Mode](#multi-agent-mode)
- [Autonomous Watch Mode](#autonomous-watch-mode)
- [Alert Rules](#alert-rules)
- [Skills](#skills)
- [Notifications](#notifications)
- [Docker](#docker)
- [Development](#development)
- [License](#license)


## Features

- **Multi-agent architecture** — Squire decomposes into specialized sub-agents (Monitor, Container, Admin, Notifier) that collaborate via [Google ADK](https://google.github.io/adk-docs/)'s transfer pattern — while maintaining a single unified persona
- **Three interfaces** — Browser-based web UI, terminal TUI, and CLI — all backed by the same agent and services
- **Skills** — file-based instructions ([Open Agent Skills spec](https://agentskills.io/specification)) that give Squire guided, repeatable behavior. Each skill is a `SKILL.md` file with YAML frontmatter + Markdown instructions — version-controllable, editable with any text editor, no database required. Execute manually or attach to watch mode for automated checks
- **Autonomous watch mode** — `squire watch` runs a headless monitoring loop that checks your systems on a schedule, takes corrective action within risk limits, and sends notifications
- **Alert rules** — Define conditions like `cpu_percent > 90` and get notified when they trigger. Manage via conversation, CLI, or web UI
- **Multi-machine management** — Connect to remote hosts over SSH and manage your entire homelab from one Squire instance
- **Built-in tools** — System info, Docker management, log reading, network diagnostics, config inspection, and guarded command execution — all targetable at any configured host
- **Risk profiles** — Control what your Squire can do: `read-only`, `cautious`, `standard`, `full-trust` — globally or per sub-agent
- **Multi-model LLM** — Powered by [LiteLLM](https://github.com/BerriAI/litellm) — use Ollama, Anthropic, OpenAI, Gemini, or any supported provider
- **Session persistence** — SQLite-backed chat history with session resume
- **Webhook notifications** — Get alerts on Discord, ntfy.sh, or any HTTP endpoint


## Quickstart

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/willdah/squire.git
cd squire
cp squire.example.toml squire.toml  # edit to taste
```

Start an interactive chat in the terminal:

```bash
uv run squire chat
```

Or launch the web interface:

```bash
uv run squire web              # opens at http://localhost:8420
```

See [Docker](#docker) for containerized deployment.


## Interfaces

### Web UI

Start with `squire web`. The browser-based interface provides:

- **Chat** — WebSocket-streamed conversation with tool call indicators and approval dialogs
- **Activity** — Timeline of tool calls, watch mode actions, and denied requests
- **Sessions** — Browse, resume, and delete past conversations
- **Skills** — Create, edit, toggle, execute, and delete skills with a form-based editor
- **Watch** — Start/stop watch mode, live-stream cycle activity, interactive tool approval with countdown timers, and runtime config changes
- **Hosts** — Host registry with reachable/unreachable status, services, and tags
- **Notifications** — Notification category overview and recent history
- **Config** — Current effective configuration viewer

The web server runs FastAPI with a Next.js frontend. Default port is `8420`.

### TUI

Start with `squire chat`. The terminal interface provides a chat pane, system status panel, activity log, and approval modals for high-risk tool calls.

| Key | Action |
|---|---|
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear chat |
| `Ctrl+G` | Toggle activity log |
| `Ctrl+S` | Toggle status panel |
| `Ctrl+X` | Clear all sessions |

### CLI

All commands are available via `squire <command>`. See [docs/cli.md](docs/cli.md) for the full reference.

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


## Configuration

See [docs/configuration.md](docs/configuration.md) for the full configuration reference with all fields, env vars, and examples.

Settings are resolved in order of precedence (highest first):

1. **Environment variables**, prefixed with `SQUIRE_*`
2. **TOML config file**, first found from:
   - `./squire.toml` (project directory)
   - `~/.config/squire/squire.toml` (user config)
   - `/etc/squire/squire.toml` (system-wide)
3. **Built-in defaults**

See [`squire.example.toml`](squire.example.toml) for all options.

### LLM Setup

Squire uses LiteLLM, so any supported model works. The default is Ollama:

```toml
[llm]
model = "ollama_chat/llama3.1:8b"
api_base = "http://localhost:11434"
```

For cloud providers, set the relevant API key env var and model string:

```toml
[llm]
model = "anthropic/claude-sonnet-4-20250514"
# Set ANTHROPIC_API_KEY env var
```

### Risk Tolerance

Control tool permissions with `risk_tolerance`:

| Tolerance | Level | Auto-allows | Needs approval |
|---|---|---|---|
| `read-only` | 1 | System info, network info, container listing | Logs, config reads, all mutations |
| `cautious` | 2 | + log viewing, config reads | Compose, systemctl, commands |
| `standard` | 3 | + compose, systemctl | Arbitrary command execution |
| `full-trust` | 5 | Everything | Nothing |

Fine-grained overrides (per-tool allow/deny/require-approval, per-agent tolerances, command and path guards) are configured in the `[guardrails]` section. See [docs/configuration.md](docs/configuration.md#guardrails----guardrails) for details.

### Remote Hosts

Connect Squire to other machines in your homelab via SSH:

```toml
[[hosts]]
name = "media-server"
address = "192.168.1.10"
user = "will"

[[hosts]]
name = "nas"
address = "192.168.1.20"
user = "will"
port = 2222
tags = ["storage"]
```

Squire connects lazily on first use via SSH key authentication (uses your ssh-agent or a configured `key_file`). Once configured, just mention a host by name in conversation and Squire will target the right machine automatically. Every tool also accepts an explicit `host` parameter to determine where it runs.

> [!NOTE]
> Remote tool calls receive a **+1 risk bump**.
>
> For example, `docker_ps` on a remote host becomes risk level 2 instead of 1.


## Multi-Agent Mode

Enable sub-agent decomposition for better tool scoping and risk isolation:

```toml
multi_agent = true
```

Squire splits into multiple specialist sub-agents:

| Sub Agent | Role | Risk Tolerance | Example Tools |
|---|---|---|---|
| Monitor | Read-only observation | `read-only` | `docker_ps`, `systemctl_status` |
| Container | Docker lifecycle | `cautious` | `docker_build`, `docker_run` |
| Admin | Systemd and commands | `standard` | `systemctl_start`, `ls` |
| Notifier | Alerts | `read-only` | `send_notification` |

The LLM routes requests to the right specialist automatically, while the user always interacts with the main Squire persona.


## Autonomous Watch Mode

> [!WARNING]
> Watch mode is **experimental** and can take actions on your system. Start with `tolerance = "read-only"` under `[guardrails.watch]` and confirm alert rules before enabling any corrective behavior.

Turn Squire into a full-time guardian for your homelab. Watch mode runs a headless monitoring loop that:

- gathers system snapshots (CPU, memory, disk, Docker, services, etc.)
- evaluates configured alert rules and triggers notifications when thresholds are crossed
- optionally takes corrective action (within configured risk limits)
- logs activity to stdout (ideal for systemd/journald) and sends webhook notifications for actions, blocks, and alerts

```bash
squire watch              # start watch mode
squire watch status       # check current status
```

Watch mode can also be started and supervised from the [web UI](#web-ui), which provides live streaming, cycle history, and interactive tool approval with countdown timers.

Watch mode uses the same risk tolerance settings as interactive mode. Risk policy for watch mode is configured under `[guardrails.watch]`. See [docs/configuration.md](docs/configuration.md#watch-mode-risk-overrides----guardrailswatch) for details.


## Alert Rules

Define conditions that trigger notifications when system metrics cross thresholds:

```bash
squire alerts add --name "disk-full" --condition "disk_percent > 90" --severity warning
squire alerts add --name "high-cpu" --condition "cpu_percent > 85" --host all
squire alerts list
squire alerts disable disk-full
squire alerts remove high-cpu
```

Or manage them conversationally. Ask Squire to "alert me if disk usage exceeds 90%".

Conditions use a safe DSL: `<field> <op> <value>` where field is a snapshot metric (`cpu_percent`, `memory_used_mb`, etc.) and op is `>`, `<`, `>=`, `<=`, `==`, `!=`.


## Skills

Define reusable instructions for Squire to follow. Each skill is a directory with a `SKILL.md` file:

```
skills/
  restart-on-error/
    SKILL.md
```

A `SKILL.md` uses YAML frontmatter for metadata and freeform Markdown for instructions:

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

The `name` and `description` fields are required by the [Open Agent Skills spec](https://agentskills.io/specification). Names must be lowercase letters, numbers, and hyphens (max 64 chars). Squire-specific fields (`host`, `trigger`, `enabled`) go under `metadata`.

Manage skills via CLI:

```bash
squire skills list
squire skills show restart-on-error
squire skills add --name my-skill --description "What this skill does" --instructions-file instructions.md
squire skills remove my-skill
squire skills enable my-skill
squire skills disable my-skill
```

The web UI Skills page (`/skills`) provides full management: browse, create/edit, toggle, delete, and execute skills. Executing a skill opens a new chat session with the instructions pre-loaded — Squire automatically begins following them.

### Triggers

- **`manual`** — execute on demand from the web UI, CLI, or API
- **`watch`** — automatically appended to the check-in prompt during each watch mode cycle

The skills directory is configurable via `[skills]` in `squire.toml` (default `~/.local/share/squire/skills`).


## Notifications

Squire can send webhook notifications for events like watch mode alerts, tool call denials, and corrective actions. Supports Discord, ntfy.sh, or any HTTP endpoint.

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

See [docs/configuration.md](docs/configuration.md#notifications----notifications) for the full list of event categories and webhook options.


## Docker

Build and run Squire in a container:

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

The container stores its SQLite database at `/data` (mount a volume for persistence). The entrypoint accepts any Squire command (`chat`, `web`, `watch`, etc.).


## Development

```bash
make install          # install Python + frontend dependencies
make ci               # lint + format check + tests (mirrors CI)
make help             # show all available targets
```

Common targets:

```bash
make lint             # ruff linter
make format           # auto-format Python
make test             # pytest

make web-dev          # Next.js dev server (hot reload)
make web-build        # Next.js production build

make chat             # start TUI
make web              # start web interface (with --reload)
make watch            # start watch mode
```

Or run commands directly:

```bash
uv run pytest tests/test_tools/test_docker.py   # single test file
uv run squire web --port 9000                    # custom port
```


## License

[MIT](LICENSE) — William Ahern
