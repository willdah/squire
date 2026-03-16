<div align="center">
  <h1>Squire</h1>
  <img src="docs/assets/squire_logo_wide.png" alt="Squire" width="100%">
  <p><strong>Your homelab's faithful attendant.</strong></p>
</div>

---

- [Features](#features)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
  - [LLM Setup](#llm-setup)
  - [Risk Tolerance](#risk-tolerance)
  - [Personalization](#personalization)
  - [Remote Hosts](#remote-hosts)
  - [Multi-Agent Mode](#multi-agent-mode)
  - [Autonomous Watch Mode](#autonomous-watch-mode)
    - [Running watch mode](#running-watch-mode)
  - [Alert Rules](#alert-rules)
- [CLI](#cli)
- [Development](#development)
- [License](#license)


## Features

- **Multi-agent architecture** — Squire decomposes into specialized sub-agents (Monitor, Container, Admin, Notifier) that collaborate via [Google ADK](https://google.github.io/adk-docs/)'s transfer pattern — while maintaining a single unified persona
- **Autonomous watch mode** — `squire watch` runs a headless monitoring loop that checks your systems on a schedule, takes corrective action within risk limits, and sends notifications
- **Alert rules** — Define conditions like `cpu_percent > 90` and get notified when they trigger. Manage via conversation, CLI, or TUI
- **Multi-machine management** — Connect to remote hosts over SSH and manage your entire homelab from one Squire instance
- **Interactive TUI** — Chat with your Squire in a terminal interface with status panel, log viewer, and approval modals
- **Built-in tools** — System info, Docker management, log reading, network diagnostics, config inspection, and guarded command execution — all targetable at any configured host
- **Risk profiles** — Control what your Squire can do: `read-only`, `cautious`, `standard`, `full-trust` — globally or per sub-agent
- **Multi-model LLM** — Powered by [LiteLLM](https://github.com/BerriAI/litellm) — use Ollama, Anthropic, OpenAI, Gemini, or any supported provider. Latest functionality tested with Qwen 3.5 (35B) on Ollama
- **Session persistence** — SQLite-backed chat history with session resume
- **Webhook notifications** — Get alerts on Discord, ntfy.sh, or any HTTP endpoint
- **Personality profiles** — Choose from built-in squire personalities (Rook, Cedric, Wynn) or create your own

## Quickstart

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/wahern/squire.git
cd squire
cp squire.example.toml squire.toml  # edit to taste
uv run squire chat
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

### Risk Tolerance

Control tool permissions with `risk_tolerance`:

| Tolerance | Level | Auto-allows | Needs approval |
|---|---|---|---|
| `read-only` | 1 | System info, network info, container listing | Logs, config reads, all mutations |
| `cautious` | 2 | + log viewing, config reads | Compose, systemctl, commands |
| `standard` | 3 | + compose, systemctl | Arbitrary command execution |
| `full-trust` | 5 | Everything | Nothing |

### Personalization

Give your Squire an identity:

```toml
house = "Agents"              # Your house name
squire_profile = "rook"      # Built-in profile: rook, cedric, wynn
squire_name = "Gareth"       # Custom name (overrides profile name)
```

**Built-in profiles:**
- **Rook** — Watchful and methodical. Concise responses, confirms before acting.
- **Cedric** — Confident and proactive. Anticipates problems, takes initiative.
- **Wynn** — Thoughtful and educational. Explains reasoning, teaches as it goes.

### Remote Hosts

Connect Squire to other machines in your homelab via SSH:

```toml
[[hosts]]
name = "media-server"
address = "192.168.1.10"
user = "test_user"

[[hosts]]
name = "nas"
address = "192.168.1.20"
user = "test_user"
port = 2222
tags = ["storage"]
```

Squire connects lazily on first use via SSH key authentication (uses your ssh-agent or a configured `key_file`). Once configured, just mention a host by name in conversation and Squire will target the right machine automatically. Every tool also accepts an explicit `host` parameter to determine where it runs.

> [!NOTE]
> Remote tool calls receive a **+1 risk bump**.
>
> For example, `docker_ps` on a remote host becomes risk level 2 instead of 1.

### Multi-Agent Mode

Enable sub-agent decomposition for better tool scoping and risk isolation:

```toml
multi_agent = true
```

Squire splits into multiple specialist sub-agents.

See below for the currently built-in sub-agents.

| Sub Agent | Role | Risk Tolerance | Example Tools |
|---|---|---|---|
| Monitor | Read-only observation | `read-only` | `docker_ps`, `systemctl_status` |
| Container | Docker lifecycle | `cautious` | `docker_build`, `docker_run` |
| Admin | Systemd and commands | `standard` | `systemctl_start`, `ls` |
| Notifier | Alerts | `read-only` | `send_notification` |

The LLM routes requests to the right specialist automatically, while the user always interacts with the main Squire persona.

### Autonomous Watch Mode

Turn Squire into a full‑time guardian for your homelab.

Watch mode runs a headless monitoring loop that:

- gathers system snapshots (CPU, memory, disk, Docker, services, etc.)
- evaluates configured alert rules and triggers notifications when thresholds are crossed
- optionally takes corrective action (within configured risk limits)
- logs activity to stdout (ideal for systemd/journald) and sends webhook notifications for actions, blocks, and alerts

Watch mode uses the same risk tolerance settings as interactive mode. If a tool call exceeds the configured `watch.risk_tolerance`, it is auto‑denied, and the event is logged and notified.

#### Running watch mode

```bash
squire watch              # start watch mode
squire watch status       # check current status
```

Watch mode is designed for unattended operation: it keeps an eye on your systems, acts within safe boundaries, and surfaces anything that needs your attention.
### Alert Rules

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

## CLI

See [docs/cli.md](docs/cli.md) for the full CLI reference including all options, watch mode configuration, and alert rule syntax.

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## License

[MIT](LICENSE) — William Ahern
