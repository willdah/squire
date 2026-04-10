# Container Lifecycle Tools Design

**Date:** 2026-04-04
**Status:** Approved

## Overview

Add three consolidated container lifecycle tools to Squire, expanding the Container sub-agent from read-only monitoring to full container management. Each tool follows Approach B (consolidated, multi-action) with per-action risk levels evaluated through the action-centric risk engine.

## Motivation

Squire's existing container tools (`docker_ps`, `docker_logs`, `docker_compose`) are primarily read-only. The most common manual homelab tasks — pulling updates, recreating containers, pruning unused resources — require SSH-ing into hosts and running commands directly. These tools close that gap.

## Tools

### `docker_container`

Lifecycle management for individual containers.

**Parameters:** `action: str`, `container: str`, `force: bool = False`, `host: str = "local"`

| Action | Risk | Description |
|--------|------|-------------|
| `inspect` | 1 | Detailed container info (config, mounts, networking) |
| `start` | 3 | Start a stopped container |
| `stop` | 3 | Graceful stop (SIGTERM + timeout) |
| `restart` | 3 | Stop + start |
| `remove` | 4 | Delete a container (optional force flag, which bumps risk to 5) |

- Auto-resolves host via `registry.resolve_host_for_service(container)`.
- `force=True` on `remove` bumps risk by +1 (capped at 5).

### `docker_image`

Image management.

**Parameters:** `action: str`, `image: str = ""`, `host: str = "local"`

| Action | Risk | Description |
|--------|------|-------------|
| `list` | 1 | List images with size/tags |
| `inspect` | 1 | Image metadata and layers |
| `pull` | 2 | Pull/update an image by reference |
| `remove` | 3 | Remove an image (refuses if in use by a running container) |

### `docker_cleanup`

Pruning and resource recovery.

**Parameters:** `action: str`, `host: str = "local"`

| Action | Risk | Description |
|--------|------|-------------|
| `df` | 1 | Show Docker disk usage (`docker system df`) |
| `prune_containers` | 3 | Remove stopped containers |
| `prune_images` | 3 | Remove dangling images |
| `prune_volumes` | 4 | Remove unused volumes (data loss risk) |
| `prune_all` | 4 | Full system prune (containers + images + networks, no volumes) |

`prune_all` explicitly excludes volumes — volume pruning is a separate, deliberate action to prevent accidental data loss.

## Risk Gate Integration

### Compound Action Names

The risk gate callback (`risk_gate.py`) will construct compound action names for tools that have an `action` parameter:

```python
action_param = args.get("action", "")
action_name = f"{tool_name}:{action_param}" if action_param else tool_name
action = Action(kind="tool_call", name=action_name, parameters=args, risk=action_risk)
```

### Per-Action Risk Levels

Each new tool module exports a `RISK_LEVELS` dict mapping `"tool:action"` to risk level:

```python
RISK_LEVELS = {
    "docker_container:inspect": 1,
    "docker_container:start": 3,
    "docker_container:stop": 3,
    "docker_container:restart": 3,
    "docker_container:remove": 4,
}
```

These merge into `TOOL_RISK_LEVELS` in `__init__.py`. The risk gate looks up the compound name first, falling back to a tool-level default if no action-specific entry exists.

### Guardrails Configuration

Users can target specific actions in `squire.toml`:

```toml
[guardrails]
tools_allow = ["docker_container:inspect", "docker_image:list", "docker_cleanup:df"]
tools_deny = ["docker_cleanup:prune_volumes"]
tools_require_approval = ["docker_container:remove"]
```

### Backward Compatibility

Existing tools continue using the single `RISK_LEVEL` integer pattern. The compound name lookup falls back gracefully — no changes needed for `docker_ps`, `docker_logs`, etc.

## Watch Mode

Watch mode can auto-execute cleanup within the configured `watch_tolerance` threshold:

- `watch_tolerance = 3`: auto-prune stopped containers and dangling images, but deny volume pruning and `prune_all`.
- `watch_tolerance = 4`: auto-prune everything including volumes.

The `watch_tools_allow` / `watch_tools_deny` lists support compound names for fine-grained control:

```toml
[guardrails]
watch_tools_allow = ["docker_cleanup:prune_containers", "docker_cleanup:prune_images"]
watch_tools_deny = ["docker_cleanup:prune_volumes"]
```

## Container Agent Updates

- Three new tools added to `CONTAINER_TOOLS` in `groups.py`.
- Agent instructions updated to describe new capabilities, emphasizing that destructive actions (`remove`, `prune_*`) should be confirmed with the user in interactive mode.
- No new sub-agent needed.

## Multi-Host Support

All tools operate through `BackendRegistry`, supporting both local and SSH-connected remote hosts. Remote operations auto-escalate risk by +1 (existing behavior, capped at 5).

## Testing

Each tool gets a test file following existing patterns:

- `tests/test_tools/test_docker_container.py`
- `tests/test_tools/test_docker_image.py`
- `tests/test_tools/test_docker_cleanup.py`

Tests cover:
- Each action's happy path and error path (non-zero exit code)
- Host auto-resolution via `resolve_host_for_service`
- `force` flag risk escalation for `docker_container:remove`
- Invalid action parameter handling

Risk gate tests (`tests/test_risk_gate.py`) get new cases for compound `"tool:action"` name resolution and fallback behavior.

## Out of Scope

- Volume/network inspection actions (tracked: #40)
- PatternAnalyzer integration (tracked: #41)
- Changes to existing tools
- Frontend changes (web UI renders tool calls generically)
