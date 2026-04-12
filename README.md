<div align="center">
  <h1>Squire</h1>
  <img src="docs/assets/squire_logo_wide.png" alt="Squire" width="100%">
  <p><strong>Your homelab's faithful attendant.</strong></p>

  [![CI](https://github.com/willdah/squire/actions/workflows/ci.yml/badge.svg)](https://github.com/willdah/squire/actions/workflows/ci.yml)
  [![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
</div>

Squire is an AI-powered agent that monitors, manages, and guards your homelab. It connects to your machines over SSH, watches system health on a schedule, takes corrective action within configurable risk limits, and talks to you through a web UI or CLI.

---

- [Features](#features)
- [Quickstart](#quickstart)
- [Interfaces](#interfaces)
- [Documentation](#documentation)
- [Development](#development)
- [License](#license)


## Features

- **Multi-agent architecture** — specialized sub-agents (Monitor, Container, Admin, Notifier) collaborate via [Google ADK](https://google.github.io/adk-docs/) while presenting a single unified persona
- **Web UI + CLI** — browser interface for chat, watch, and configuration; command-line tools for automation and management
- **Autonomous watch mode** — headless monitoring loop that checks your systems, evaluates alert rules, and takes corrective action within risk limits
- **Alert rules** — define conditions like `cpu_percent > 90` and get notified when thresholds are crossed
- **Skills** — file-based instruction sets ([Open Agent Skills spec](https://openagentskills.dev)) for guided, repeatable behavior — run manually or on a watch schedule
- **Multi-machine management** — connect to remote hosts over SSH and manage your entire homelab from one instance
- **Risk profiles** — `read-only`, `cautious`, `standard`, or `full-trust` — globally or per sub-agent, with fine-grained guardrails
- **Multi-model LLM** — powered by [LiteLLM](https://github.com/BerriAI/litellm) — Ollama, Anthropic, OpenAI, Gemini, or any supported provider
- **Webhook notifications** — alerts on Discord, ntfy.sh, email, or any HTTP endpoint
- **Session persistence** — SQLite-backed chat history with session resume


## Quickstart

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/willdah/squire.git
cd squire
cp squire.example.toml squire.toml  # edit to taste
```

Launch the web interface:

```bash
uv run squire web              # opens at http://localhost:8420
```

See the [Usage Guide](docs/usage.md#docker-deployment) for Docker deployment.


## Interfaces

**Web UI** — `squire web` opens a browser-based interface with chat, activity timeline, session management, skill editor, watch mode controls with live streaming, Watch Explorer for run/session/cycle history and reports, host registry, notification history, and configuration viewer. See [Usage Guide — Web UI](docs/usage.md#web-ui).

**CLI** — All management commands are available via `squire <command>` without a running UI. See the [CLI Reference](docs/cli.md) for the full command list.


## Documentation

| Document | Description |
|---|---|
| [Usage Guide](docs/usage.md) | Web UI, CLI, configuration, remote hosts, watch mode, alerts, skills, notifications, Docker |
| [Architecture](docs/architecture.md) | System design, agent architecture, risk pipeline, tech stack, database schema |
| [CLI Reference](docs/cli.md) | All commands and options |
| [Configuration Reference](docs/configuration.md) | Full config reference with all fields, env vars, and examples |
| [Contributing](CONTRIBUTING.md) | Development setup, code conventions, testing, PR workflow |
| [Changelog](CHANGELOG.md) | Version history |


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
