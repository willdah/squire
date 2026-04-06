# Docker Web App Support

**Date:** 2026-04-05
**Status:** Approved

## Problem

The Dockerfile defaults to `squire chat` (TUI mode), which requires an interactive terminal and doesn't suit containerized deployment. The web frontend is not built into the image, and data paths are not consolidated for volume mounting.

## Design

### Multi-stage Dockerfile

**Stage 1 (Node 22-slim):** Install frontend dependencies and run `npm run build` to produce the `web/out/` static export.

**Stage 2 (Python 3.12-slim):** Install Python dependencies with `uv`, copy application source, and copy `web/out/` from the Node stage. The `_find_static_dir()` function in `src/squire/api/app.py` already looks for `web/out/` relative to the package root, so no application code changes are needed for frontend serving.

Key properties:

- `EXPOSE 8420`
- Default `CMD ["web"]` (replaces `chat`)
- `HEALTHCHECK` using the new `/api/health` endpoint
- Environment variables consolidate all persistent data under `/data`:
  - `SQUIRE_DB_PATH=/data/squire.db`
  - `SQUIRE_SKILLS_PATH=/data/skills`
  - `SQUIRE_KEYS_DIR=/data/keys`
- Single `VOLUME ["/data"]`

### Health check endpoint

New `GET /api/health` endpoint on the FastAPI app:

- Returns `{"status": "ok"}` with HTTP 200
- No database or LLM connectivity check -- just confirms the web server is responsive
- Mounted at `/api/health` alongside existing API routers
- Used by Docker `HEALTHCHECK` and compose `healthcheck:`

Implementation: a simple router in `src/squire/api/routers/health.py` included in `create_app()`.

### Configurable SSH keys directory

The keys directory is currently hardcoded to `~/.config/squire/keys/` in `src/squire/system/keys.py`. Add support for a `SQUIRE_KEYS_DIR` environment variable so Docker can redirect keys storage to `/data/keys/`.

Change `_keys_dir()` to read `os.environ.get("SQUIRE_KEYS_DIR")` with the existing `~/.config/squire/keys/` as fallback.

### docker-compose.yml

New file at project root:

```yaml
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
      - SQUIRE_LLM_MODEL=ollama_chat/llama3.1:8b
      - SQUIRE_LLM_API_BASE=http://host.docker.internal:11434
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

volumes:
  squire-data:
```

Includes commented examples for:

- Config file bind-mount (`./squire.toml:/app/squire.toml:ro`)
- Cloud provider API keys (`ANTHROPIC_API_KEY`, etc.)
- Watch mode as alternate command

### Makefile updates

- `docker-run`: expose port 8420, drop `-it` flag, run in detached mode with port mapping

### Documentation updates

Update the "Docker Deployment" section of `docs/usage.md` to cover:

- **Quickstart** with docker-compose as the recommended path
- **Ports:** 8420 (web UI + API, single port)
- **Data volume:** `/data` contains database (`squire.db`), skills, and SSH keys
- **Configuration:** env vars (primary) or bind-mount `squire.toml:/app/squire.toml:ro`
- **LLM provider setup:** Ollama via `host.docker.internal`, cloud providers via API key env vars
- **Watch mode:** override command to `watch`
- **CLI commands:** via `docker exec` or one-off `docker run`
- **Health check:** built-in, visible via `docker ps` HEALTH column
- **No TUI:** the container does not support `squire chat`

### CHANGELOG

Add entry for Docker web app support, health check endpoint, and configurable keys directory.

## Out of scope

- TUI support in Docker
- Separate frontend/backend containers
- Deep health checks (database connectivity, LLM reachability)

## Files changed

| File | Change |
|---|---|
| `docker/Dockerfile` | Multi-stage build, new defaults |
| `docker-compose.yml` | New file |
| `src/squire/api/routers/health.py` | New health check router |
| `src/squire/api/app.py` | Include health router |
| `src/squire/system/keys.py` | Configurable keys directory |
| `Makefile` | Update `docker-run` target |
| `docs/usage.md` | Rewrite Docker Deployment section |
| `CHANGELOG.md` | New entry |
