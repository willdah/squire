# Docker Web App Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Docker setup from TUI-first to web-first with a multi-stage build, health check endpoint, docker-compose, and updated documentation.

**Architecture:** Multi-stage Dockerfile (Node builds frontend, Python serves everything). All persistent data consolidated under `/data` via environment variables. A new `/api/health` endpoint supports Docker health checks.

**Tech Stack:** Docker multi-stage (Node 22-slim + Python 3.12-slim), FastAPI, docker-compose

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/squire/api/routers/health.py` | Create | Health check endpoint |
| `src/squire/api/app.py` | Modify | Include health router |
| `src/squire/system/keys.py` | Modify | Configurable keys directory via env var |
| `tests/test_health.py` | Create | Health endpoint test |
| `tests/test_keys.py` | Create | Keys directory configurability test |
| `docker/Dockerfile` | Rewrite | Multi-stage build with web default |
| `docker-compose.yml` | Create | Compose file for quickstart |
| `Makefile` | Modify | Update `docker-run` target |
| `docs/usage.md` | Modify | Rewrite Docker Deployment section |
| `CHANGELOG.md` | Modify | Add entries |

---

### Task 1: Health Check Endpoint

**Files:**
- Create: `tests/test_health.py`
- Create: `src/squire/api/routers/health.py`
- Modify: `src/squire/api/app.py:166-177`

- [ ] **Step 1: Write the failing test**

Create `tests/test_health.py`:

```python
"""Health check endpoint tests."""

from fastapi.testclient import TestClient

from squire.api.app import create_app


def test_health_returns_ok():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_health.py::test_health_returns_ok -v`
Expected: FAIL — 404 because the route doesn't exist yet.

- [ ] **Step 3: Create the health router**

Create `src/squire/api/routers/health.py`:

```python
"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health():
    """Lightweight liveness check — confirms the web server is responsive."""
    return {"status": "ok"}
```

- [ ] **Step 4: Register the health router in the app**

In `src/squire/api/app.py`, add the import alongside the existing router imports (around line 37) and mount it alongside the other routers (around line 167).

Add to the import block where other routers are imported:

```python
from .routers import health
```

Add after the existing `app.include_router(...)` lines (before the `if static_dir:` block):

```python
app.include_router(health.router, prefix="/api/health", tags=["health"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_health.py src/squire/api/routers/health.py src/squire/api/app.py
git commit -m "feat(api): add /api/health endpoint for Docker health checks"
```

---

### Task 2: Configurable SSH Keys Directory

**Files:**
- Create: `tests/test_keys.py`
- Modify: `src/squire/system/keys.py:16-18`

- [ ] **Step 1: Write the failing test**

Create `tests/test_keys.py`:

```python
"""SSH keys directory configurability tests."""

from pathlib import Path

from squire.system.keys import _keys_dir


def test_keys_dir_default():
    """Without env var, uses ~/.config/squire/keys/."""
    result = _keys_dir()
    assert result == Path.home() / ".config" / "squire" / "keys"


def test_keys_dir_from_env(monkeypatch, tmp_path):
    """SQUIRE_KEYS_DIR overrides the default."""
    custom = tmp_path / "custom-keys"
    monkeypatch.setenv("SQUIRE_KEYS_DIR", str(custom))
    result = _keys_dir()
    assert result == custom
```

- [ ] **Step 2: Run tests to verify the env var test fails**

Run: `uv run pytest tests/test_keys.py -v`
Expected: `test_keys_dir_default` PASSES, `test_keys_dir_from_env` FAILS because `_keys_dir()` ignores the env var.

- [ ] **Step 3: Update `_keys_dir()` to read env var**

In `src/squire/system/keys.py`, replace the `_keys_dir` function:

Old:
```python
def _keys_dir() -> Path:
    """Return the keys storage directory."""
    return Path.home() / ".config" / "squire" / "keys"
```

New:
```python
def _keys_dir() -> Path:
    """Return the keys storage directory.

    Reads SQUIRE_KEYS_DIR env var, falling back to ~/.config/squire/keys/.
    """
    if env := os.environ.get("SQUIRE_KEYS_DIR"):
        return Path(env)
    return Path.home() / ".config" / "squire" / "keys"
```

Also update the module docstring — replace the first two lines:

Old:
```python
"""SSH key management — generate, retrieve, and delete ed25519 key pairs.

Keys are stored in ~/.config/squire/keys/ with one file per host:
```

New:
```python
"""SSH key management — generate, retrieve, and delete ed25519 key pairs.

Keys are stored in SQUIRE_KEYS_DIR (default ~/.config/squire/keys/) with one file per host:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_keys.py -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_keys.py src/squire/system/keys.py
git commit -m "feat(keys): make SSH keys directory configurable via SQUIRE_KEYS_DIR"
```

---

### Task 3: Multi-Stage Dockerfile

**Files:**
- Rewrite: `docker/Dockerfile`

- [ ] **Step 1: Rewrite the Dockerfile**

Replace the entire contents of `docker/Dockerfile` with:

```dockerfile
# Stage 1: Build the Next.js frontend
FROM node:22-slim AS frontend

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency metadata first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application source
COPY src/ src/

# Copy frontend build from Stage 1
COPY --from=frontend /web/out web/out

# Consolidate all persistent data under /data
ENV SQUIRE_DB_PATH=/data/squire.db
ENV SQUIRE_SKILLS_PATH=/data/skills
ENV SQUIRE_KEYS_DIR=/data/keys
ENV SQUIRE_RISK_PROFILE=cautious

VOLUME ["/data"]
EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/health')"]

ENTRYPOINT ["uv", "run", "squire"]
CMD ["web"]
```

- [ ] **Step 2: Verify the build works**

Run: `docker build -f docker/Dockerfile -t squire .`
Expected: Both stages complete successfully. The image should contain `web/out/` with the static export.

- [ ] **Step 3: Verify the container starts and health check passes**

Run: `docker run --rm -d --name squire-test -p 8420:8420 -e SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b squire`

Wait ~15 seconds, then:

Run: `curl -s http://localhost:8420/api/health`
Expected: `{"status":"ok"}`

Run: `docker ps --filter name=squire-test --format '{{.Status}}'`
Expected: Shows `(healthy)` after the start period.

Clean up: `docker stop squire-test`

- [ ] **Step 4: Commit**

```bash
git add docker/Dockerfile
git commit -m "feat(docker): multi-stage build with web frontend and health check"
```

---

### Task 4: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create the compose file**

Create `docker-compose.yml` at the project root:

```yaml
# Squire — AI-powered homelab monitoring and management
# Quick start: docker compose up -d
# Web UI: http://localhost:8420

services:
  squire:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8420:8420"
    volumes:
      - squire-data:/data
    environment:
      # LLM provider — configure one of these:
      # Ollama (default — assumes Ollama running on the Docker host)
      - SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b
      - SQUIRE_LLM_API_BASE=http://host.docker.internal:11434
      # Anthropic:
      # - SQUIRE_LLM_MODEL=anthropic/claude-sonnet-4-20250514
      # - ANTHROPIC_API_KEY=sk-ant-...
      # OpenAI:
      # - SQUIRE_LLM_MODEL=openai/gpt-4o
      # - OPENAI_API_KEY=sk-...
      # Google Gemini:
      # - SQUIRE_LLM_MODEL=gemini/gemini-2.0-flash
      # - GEMINI_API_KEY=...

      # Risk tolerance (read-only | cautious | standard | full-trust)
      # - SQUIRE_RISK_TOLERANCE=cautious
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

    # To mount a config file instead of using env vars:
    # volumes:
    #   - squire-data:/data
    #   - ./squire.toml:/app/squire.toml:ro

    # To run watch mode instead of the web UI:
    # command: watch

volumes:
  squire-data:
```

- [ ] **Step 2: Verify compose starts**

Run: `docker compose up -d --build`
Expected: Container starts, becomes healthy.

Run: `curl -s http://localhost:8420/api/health`
Expected: `{"status":"ok"}`

Clean up: `docker compose down`

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(docker): add docker-compose.yml for quickstart deployment"
```

---

### Task 5: Update Makefile

**Files:**
- Modify: `Makefile:79-85`

- [ ] **Step 1: Update the docker-run target**

In `Makefile`, replace the `docker-run` target:

Old:
```makefile
.PHONY: docker-run
docker-run: ## Run Docker container
	docker run --rm -it -v squire-data:/data squire
```

New:
```makefile
.PHONY: docker-run
docker-run: ## Run Docker container (web UI on port 8420)
	docker run --rm -d -p 8420:8420 -v squire-data:/data --name squire squire
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "chore: update docker-run target for web UI"
```

---

### Task 6: Update Documentation

**Files:**
- Modify: `docs/usage.md:471-501`

- [ ] **Step 1: Rewrite the Docker Deployment section**

In `docs/usage.md`, replace everything from `## Docker Deployment` (line 475) to the end of the file with:

```markdown
## Docker Deployment

The Docker image runs the **web interface** by default. The image includes a pre-built frontend, so no separate Node.js process is needed.

### Quick Start (docker-compose)

The recommended way to run Squire in Docker:

```bash
docker compose up -d
```

The web UI is available at **http://localhost:8420**.

The default `docker-compose.yml` assumes Ollama is running on the Docker host. Edit the `environment` section to configure your LLM provider — see the comments in the file for examples with Anthropic, OpenAI, and Gemini.

### Manual Docker Run

```bash
# Build the image
make docker-build
# or: docker build -f docker/Dockerfile -t squire .

# Run the web UI
docker run -d -p 8420:8420 -v squire-data:/data \
  -e SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b \
  -e SQUIRE_LLM_API_BASE=http://host.docker.internal:11434 \
  --name squire squire
```

### Ports

| Port | Service |
|---|---|
| **8420** | Web UI + REST API + WebSocket (single port) |

### Data Volume

All persistent data lives under `/data` inside the container. Mount a named volume or host directory to preserve state across restarts:

| Path | Contents |
|---|---|
| `/data/squire.db` | SQLite database (sessions, events, alert rules, watch state) |
| `/data/skills/` | Skill definitions (Open Agent Skills format) |
| `/data/keys/` | SSH key pairs for managed remote hosts |

```bash
# Use a named volume (recommended)
docker run -v squire-data:/data ...

# Or bind-mount a host directory
docker run -v /opt/squire/data:/data ...
```

### Configuration

Configuration can be provided via environment variables or a config file:

**Environment variables** (recommended for Docker):

```bash
docker run -d -p 8420:8420 -v squire-data:/data \
  -e SQUIRE_LLM_MODEL=anthropic/claude-sonnet-4-20250514 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e SQUIRE_RISK_TOLERANCE=standard \
  squire
```

**Config file** (bind-mount):

```bash
docker run -d -p 8420:8420 \
  -v squire-data:/data \
  -v ./squire.toml:/app/squire.toml:ro \
  squire
```

See the [Configuration Reference](configuration.md) for all available options.

### LLM Provider Setup

**Ollama (local):** If Ollama runs on the Docker host, use `host.docker.internal` to reach it:

```bash
-e SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b
-e SQUIRE_LLM_API_BASE=http://host.docker.internal:11434
```

> **Note:** `host.docker.internal` works on Docker Desktop (macOS/Windows). On Linux, add `--add-host=host.docker.internal:host-gateway` to your `docker run` command, or use the host's LAN IP address.

**Cloud providers:** Set the model and API key as environment variables:

```bash
# Anthropic
-e SQUIRE_LLM_MODEL=anthropic/claude-sonnet-4-20250514 -e ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
-e SQUIRE_LLM_MODEL=openai/gpt-4o -e OPENAI_API_KEY=sk-...

# Google Gemini
-e SQUIRE_LLM_MODEL=gemini/gemini-2.0-flash -e GEMINI_API_KEY=...
```

### Watch Mode

To run autonomous monitoring instead of the web UI, override the command:

```bash
# docker-compose: uncomment "command: watch" in docker-compose.yml

# Manual:
docker run -d -v squire-data:/data \
  -e SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b \
  -e SQUIRE_LLM_API_BASE=http://host.docker.internal:11434 \
  --name squire-watch squire watch
```

You can run both side by side — the web UI on one container and watch mode on another — sharing the same data volume:

```bash
docker run -d -p 8420:8420 -v squire-data:/data --name squire-web squire
docker run -d -v squire-data:/data --name squire-watch squire watch
```

### CLI Commands

Run one-off CLI commands against a running container or the data volume:

```bash
# Against a running container
docker exec squire uv run squire alerts list
docker exec squire uv run squire sessions list

# One-off with the data volume
docker run --rm -v squire-data:/data squire alerts list
docker run --rm -v squire-data:/data squire hosts list
```

### Health Check

The container includes a built-in health check (`GET /api/health`) that verifies the web server is responsive. Docker reports health status in `docker ps`:

```
CONTAINER ID   IMAGE    STATUS                    PORTS
abc123         squire   Up 2 minutes (healthy)    0.0.0.0:8420->8420/tcp
```

The health check runs every 30 seconds with a 10-second startup grace period.
```

- [ ] **Step 2: Commit**

```bash
git add docs/usage.md
git commit -m "docs: rewrite Docker deployment section for web-first container"
```

---

### Task 7: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md:10-14`

- [ ] **Step 1: Add changelog entries**

In `CHANGELOG.md`, add the following entries under `## [Unreleased]` → `### Added` (after the existing Watch entries at line 14):

```markdown
- **Docker:** Multi-stage Dockerfile that builds the Next.js frontend and serves the web UI by default; includes `HEALTHCHECK` directive
- **Docker:** `docker-compose.yml` quickstart with volume, port, and LLM provider configuration
- **API:** `GET /api/health` liveness endpoint returning `{"status": "ok"}`
- **Config:** `SQUIRE_KEYS_DIR` environment variable to override the SSH keys storage directory (default `~/.config/squire/keys/`)
```

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/ tests/`
Expected: No errors.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests pass including new health and keys tests.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entries for Docker web app support"
```
