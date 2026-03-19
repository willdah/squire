# CLAUDE.md

## Project overview

Squire is an AI-powered homelab monitoring and management agent. It uses Google ADK for multi-agent orchestration with four specialized sub-agents (Monitor, Container, Admin, Notifier) behind a single "Squire" persona. It provides three interfaces: a TUI (Textual), a web UI (Next.js + FastAPI), and a CLI.

## Tech stack

**Backend (Python 3.12+):**
- Google ADK — agent orchestration
- FastAPI + Uvicorn — web API
- Typer — CLI
- Textual — TUI
- LiteLLM — LLM provider abstraction
- Pydantic / Pydantic Settings — config and validation
- aiosqlite — SQLite database
- asyncssh — remote host management
- httpx — HTTP client
- agent-risk-engine — local package for risk evaluation (zero external deps)

**Frontend (`web/`, Next.js 16):**
- React 19 with App Router
- shadcn/ui v4 + Tailwind CSS v4
- Recharts — trend charts
- SWR — data fetching
- WebSocket — real-time chat

**Tooling:**
- uv — package manager
- Hatchling — build backend
- ruff — linter and formatter
- pytest + pytest-asyncio — testing
- GitHub Actions — CI (Python 3.12 + 3.13)

## Directory structure

```
src/squire/              Main application
  agents/                ADK agent definitions
  api/                   FastAPI routers (chat, system, sessions, alerts, etc.)
  callbacks/             Risk gate implementation
  config/                Config loaders (app, llm, database, hosts)
  database/              SQLite service
  instructions/          Dynamic system prompts for agents
  notifications/         Webhook dispatcher & alert evaluator
  schemas/               Pydantic models
  system/                Backend registry (local/SSH execution)
  tools/                 System interaction tools (async, return str)
  tui/                   Textual TUI components
  agent.py               Root agent builder
  approval.py            Approval provider protocols
  cli.py                 Typer CLI entry point
  main.py                Orchestration & snapshot collection
  watch.py               Autonomous watch loop

packages/
  agent-risk-engine/     Standalone risk evaluation library

web/                     Next.js frontend
  src/app/               Pages (chat, sessions, hosts, notifications, config, activity)
  src/components/        UI components
  src/hooks/             Custom React hooks
  src/lib/               API client, types, utilities

tests/                   pytest suite
  conftest.py            MockBackend, MockRegistry fixtures
  test_tools/            Tool functionality tests
  test_agents/           Agent routing tests
  test_callbacks/        Risk gate tests
  test_notifications/    Alert/webhook tests

docs/                    User documentation
docker/                  Docker configuration
```

## Commands

Common tasks are available via `make`. Run `make help` for the full list.

```bash
make install       # Install Python + frontend dependencies
make lint          # Ruff linter
make format        # Auto-format Python
make test          # pytest
make ci            # Lint + format check + test (mirrors CI)

make web-dev       # Next.js dev server
make web-build     # Next.js production build

make chat          # TUI chat interface
make web           # Web interface (FastAPI, --reload)
make watch         # Autonomous watch mode

make docker-build  # Build Docker image
make clean         # Remove caches and build artifacts
```

Or invoke directly:

```bash
uv run pytest tests/test_tools/test_docker.py   # Single test file
uv run squire web --port 9000                    # Custom port
```

## Code conventions

- **Python 3.12+** — use modern syntax (`X | Y` unions, `match` statements, etc.)
- **Line length:** 120 characters
- **Ruff rules:** E, F, I (isort), UP (pyupgrade)
- **Async throughout** — all tool functions are `async def` and return `str`
- **Error handling in tools:** use the `safe_tool` decorator; prefer returning error strings over raising exceptions so the LLM can reason about failures
- **Global service access:** tools get BackendRegistry, DatabaseService, etc. via module-level getter functions (not DI)
- **Config precedence:** env vars > `squire.toml` > defaults (Pydantic Settings)
- **Approval providers:** frontends implement `SyncApprovalProvider` or `AsyncApprovalProvider` protocols
- **Tests:** pytest with `asyncio_mode = "auto"`, use `MockBackend`/`MockRegistry` from `conftest.py` for system calls
- **Never expose internal agent names** (Monitor, Container, Admin, Notifier) to the user — present a single "Squire" persona across all interfaces
- **Always update `CHANGELOG.md`** when making code changes

## CI

GitHub Actions runs on every push/PR to `main`:
1. `ruff check` (lint)
2. `ruff format --check` (format verification)
3. `pytest` (tests)

All three must pass. Matrix: Python 3.12 and 3.13.
