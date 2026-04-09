# Contributing to Squire

Thanks for your interest in contributing. This document covers everything you need to go from zero to a merged pull request.

For questions, open a [GitHub issue](https://github.com/willdah/squire/issues) rather than emailing directly — that way the answer benefits everyone.

## Prerequisites

- **Python 3.12+** — Squire uses modern syntax throughout (`X | Y` unions, `match` statements, etc.)
- **[uv](https://docs.astral.sh/uv/)** — the project's package manager; `pip install` is not supported
- **Node.js 18+** — only needed if you're touching the frontend (`web/`)
- **Docker** — optional, required for the Docker tool tests

## Development Setup

```bash
git clone https://github.com/willdah/squire.git
cd squire
make install    # installs Python + frontend dependencies
make ci         # lint + format check + tests (mirrors CI)
```

The `make install` target runs `uv sync --dev` and `npm install` in `web/`. If you're only working on the backend, `uv sync --dev` is sufficient.

## Project Structure

```
src/squire/              Main application
  agents/                ADK agent definitions
  api/                   FastAPI routers (chat, system, sessions, alerts, skills, etc.)
  callbacks/             Risk gate implementation
  config/                Config loaders (app, llm, database, hosts, skills)
  database/              SQLite service
  instructions/          Dynamic system prompts for agents
  skills/                File-based skill service (Open Agent Skills spec)
  notifications/         Webhook dispatcher & alert evaluator
  system/                Backend registry (local/SSH execution)
  tools/                 System interaction tools (async, return str)
  agent.py               Root agent builder
  cli.py                 Typer CLI entry point
  main.py                Snapshot helpers & session listing (shared by API, watch, CLI)
  watch.py               Autonomous watch loop

web/                     Next.js frontend
  src/app/               Pages (chat, skills, sessions, hosts, notifications, config, activity)
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

## Code Conventions

### Python

- **Python 3.12+** — use modern syntax: `X | Y` unions, `match` statements, `tomllib`, etc.
- **Line length:** 120 characters
- **Formatter/linter:** ruff with rule sets E, F, I (isort), UP (pyupgrade)
- **Async throughout** — all tool functions are `async def` and return `str`
- **Error handling in tools** — return error strings instead of raising exceptions; the LLM can reason about a returned error string, not a crash
- **Global service access** — tools get `BackendRegistry`, `DatabaseService`, etc. from module-level getter functions in `src/squire/tools/_registry.py`, not via dependency injection
- **Config precedence** — env vars > `squire.toml` > defaults (Pydantic Settings)

### Single Persona

Never expose internal agent names (Monitor, Container, Admin, Notifier) through any user-facing surface — UI text, error messages, log lines that users might see, or documentation. Present everything as the single "Squire" persona.

## Adding a New Tool

Tools live in `src/squire/tools/`. Each tool is a plain async function in its own module. Here's the full workflow:

**1. Create `src/squire/tools/my_tool.py`**

```python
"""my_tool — brief description of what it does."""

import json
import logging

from ._registry import get_registry

logger = logging.getLogger(__name__)

RISK_LEVEL = 1  # 1=read-only info, 5=destructive/irreversible

async def my_tool(host: str = "local") -> str:
    """One-line summary shown to the agent as the tool description.

    Args:
        host: Target host name (default "local").

    Returns a JSON object with ...
    """
    backend = get_registry().get(host)
    result = await backend.run(["some", "command"])
    if result.returncode != 0:
        return f"Error: command failed: {result.stderr}"
    return json.dumps({"output": result.stdout.strip()})
```

For tools with multiple actions at different risk levels, use `RISK_LEVELS: dict[str, int]` with `"tool_name:action"` keys instead of a single `RISK_LEVEL`.

**2. Register the tool in `src/squire/tools/__init__.py`**

```python
# Add the import:
from .my_tool import RISK_LEVEL as _mt_risk
from .my_tool import my_tool

# Add to ALL_TOOLS:
ALL_TOOLS = [
    ...
    safe_tool(my_tool),
]

# Add to TOOL_RISK_LEVELS:
TOOL_RISK_LEVELS: dict[str, int] = {
    ...
    "my_tool": _mt_risk,
}
```

The `safe_tool` wrapper is applied here at registration time, not in the tool module itself.

**3. Write tests in `tests/test_tools/test_my_tool.py`**

Use `mock_backend` and `mock_registry` fixtures from `tests/conftest.py` to avoid shelling out during tests:

```python
from squire.tools import my_tool

async def test_my_tool_success(mock_registry, mock_backend):
    from squire.system.backend import CommandResult
    mock_backend.set_response("some", CommandResult(returncode=0, stdout="hello\n", stderr=""))
    result = await my_tool()
    assert "hello" in result

async def test_my_tool_error(mock_registry, mock_backend):
    from squire.system.backend import CommandResult
    mock_backend.set_response("some", CommandResult(returncode=1, stdout="", stderr="not found"))
    result = await my_tool()
    assert "Error" in result
```

## Testing

```bash
make test                                          # run full suite
uv run pytest tests/test_tools/test_system_info.py # single file
uv run pytest -v                                   # verbose output
uv run pytest -k "docker"                          # filter by name
```

A few things to know:

- **`asyncio_mode = "auto"`** is set in `pyproject.toml`. You do not need `@pytest.mark.asyncio` on async test functions.
- **`MockBackend`** lets you register canned `CommandResult` responses for specific command prefixes. Tests never shell out.
- **`MockRegistry`** wraps a `MockBackend` and installs it as the global registry for the duration of the test, then tears it down cleanly.
- The `mock_registry` fixture calls `set_registry(registry)` before yielding and `set_registry(None)` after — always use `mock_registry` (not `mock_backend` alone) when testing code that calls `get_registry()`.
- The `db` fixture provides a temporary `DatabaseService` backed by a file in `tmp_path`.

Test directories map to subsystems: `test_tools/` for individual tools, `test_agents/` for agent routing logic, `test_callbacks/` for the risk gate, `test_notifications/` for alerts and webhooks.

## Pull Request Workflow

1. Create a branch from `main`
2. Make your changes, keeping commits focused
3. Update `CHANGELOG.md` (see below)
4. Run `make ci` — all checks must pass before opening a PR
5. Open a pull request against `main`

CI runs `ruff check`, `ruff format --check`, and `pytest` on Python 3.12 and 3.13. A red CI is a blocker.

Keep pull requests scoped. A PR that fixes a bug and adds an unrelated feature will be asked to split. A PR that adds a tool alongside its tests and a changelog entry is ideal.

## Changelog

Update `CHANGELOG.md` with every code change — no exceptions. Follow [Keep a Changelog](https://keepachangelog.com/) format: add entries under `## [Unreleased]` in the appropriate subsection (`Added`, `Changed`, `Fixed`, `Removed`).

One-line entries are fine for small changes. For anything that affects behavior, include enough context that someone reading the changelog without the diff can understand what changed and why.

## Reporting Issues

Open a [GitHub issue](https://github.com/willdah/squire/issues) with:

- Steps to reproduce
- Expected vs. actual behavior
- Python version and OS
- Squire version (`squire version`)

Include relevant log output if available. Issues without reproduction steps take much longer to triage.
