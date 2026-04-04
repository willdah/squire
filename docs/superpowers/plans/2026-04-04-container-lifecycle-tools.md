# Container Lifecycle Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three consolidated container lifecycle tools (`docker_container`, `docker_image`, `docker_cleanup`) with per-action risk levels and compound action name resolution in the risk gate.

**Architecture:** Each tool is a multi-action async function following the existing `docker_compose` pattern. The risk gate is updated to construct compound `"tool:action"` names for tools that have an `action` parameter, enabling per-action allow/deny/approve rules in guardrails config. Risk levels are exported as a `RISK_LEVELS` dict (not a single int) for action-level granularity.

**Tech Stack:** Python 3.12+, Google ADK, agent-risk-engine, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-04-container-lifecycle-tools-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/squire/tools/docker_container.py` | Create | Container lifecycle actions (inspect, start, stop, restart, remove) |
| `src/squire/tools/docker_image.py` | Create | Image management actions (list, inspect, pull, remove) |
| `src/squire/tools/docker_cleanup.py` | Create | Pruning and resource recovery actions (df, prune_containers, prune_images, prune_volumes, prune_all) |
| `src/squire/tools/__init__.py` | Modify | Register new tools and risk levels |
| `src/squire/tools/groups.py` | Modify | Add new tools to CONTAINER_TOOLS group |
| `src/squire/callbacks/risk_gate.py` | Modify | Compound `"tool:action"` name resolution |
| `src/squire/instructions/container_agent.py` | Modify | Update agent instructions for new tools |
| `tests/test_tools/test_docker_container.py` | Create | Tests for docker_container tool |
| `tests/test_tools/test_docker_image.py` | Create | Tests for docker_image tool |
| `tests/test_tools/test_docker_cleanup.py` | Create | Tests for docker_cleanup tool |
| `tests/test_callbacks/test_risk_gate_factory.py` | Modify | Tests for compound action name resolution |
| `CHANGELOG.md` | Modify | Document new tools |

---

## Task 1: Risk Gate — Compound Action Name Resolution

Update the risk gate to construct `"tool:action"` compound names when a tool call includes an `action` parameter. This must land first because the new tools depend on per-action risk resolution.

**Files:**
- Modify: `src/squire/callbacks/risk_gate.py:71-86`
- Test: `tests/test_callbacks/test_risk_gate_factory.py`

- [ ] **Step 1: Write failing tests for compound action name resolution**

Add a new test class to `tests/test_callbacks/test_risk_gate_factory.py`:

```python
class TestCompoundActionNames:
    @pytest.mark.asyncio
    async def test_action_param_creates_compound_name(self):
        """Tools with an 'action' param should use 'tool:action' for risk lookup."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:read": 1, "my_tool:write": 4},
        )
        # read action (risk 1) should be allowed at threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "read"},
            _make_context(threshold=3),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_compound_name_high_risk_action_blocked(self):
        """High-risk actions within a tool should be blocked appropriately."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:read": 1, "my_tool:write": 4},
        )
        # write action (risk 4) should need approval at threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "write"},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_action_param_uses_tool_name(self):
        """Tools without an 'action' param should use tool name directly (backward compat)."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
        )
        result = await gate(
            _make_tool("system_info"),
            {"host": "local"},
            _make_context(threshold=3),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_compound_name_remote_host_escalation(self):
        """Remote host escalation should apply to compound action risk levels."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:start": 3},
        )
        # risk 3 + remote bump = 4, which exceeds threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "start", "host": "remote-server"},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_unknown_compound_action_denied(self):
        """An action not in the risk levels dict should be denied."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:read": 1},
        )
        result = await gate(
            _make_tool("my_tool"),
            {"action": "destroy"},
            _make_context(threshold=5),
        )
        assert result is not None
        assert "unknown" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_force_flag_bumps_risk(self):
        """force=True should escalate risk by +1."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:remove": 3},
        )
        # risk 3 + force bump = 4, which exceeds threshold 3
        result = await gate(
            _make_tool("my_tool"),
            {"action": "remove", "force": True},
            _make_context(threshold=3),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_force_false_no_bump(self):
        """force=False should not escalate risk."""
        gate = create_risk_gate(
            tool_risk_levels={"my_tool:remove": 3},
        )
        result = await gate(
            _make_tool("my_tool"),
            {"action": "remove", "force": False},
            _make_context(threshold=3),
        )
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_callbacks/test_risk_gate_factory.py::TestCompoundActionNames -v`
Expected: FAIL — `test_action_param_creates_compound_name` fails because `my_tool` is not in `scoped_risk_levels`

- [ ] **Step 3: Implement compound action name resolution in risk_gate.py**

In `src/squire/callbacks/risk_gate.py`, replace lines 70-86 with:

```python
        # Resolve compound action name: "tool:action" for tools with an action param
        action_param = args.get("action")
        if action_param:
            compound_name = f"{tool_name}:{action_param}"
        else:
            compound_name = tool_name

        # Unknown tools/actions (not in our scope and not ADK internal) are denied
        if compound_name not in scoped_risk_levels:
            return {"error": f"Blocked: unknown tool '{compound_name}'."}

        tool_risk = scoped_risk_levels[compound_name]

        # Bump risk for remote host operations
        host = args.get("host", "local")
        if host != "local":
            tool_risk = min(tool_risk + 1, 5)

        # Bump risk for forced operations
        if args.get("force"):
            tool_risk = min(tool_risk + 1, 5)

        # Load the risk evaluator from session state
        evaluator = tool_context.state.get("risk_evaluator")
        if not evaluator or not isinstance(evaluator, RiskEvaluator):
            evaluator = RiskEvaluator(rule_gate=RuleGate())

        action = Action(kind="tool_call", name=compound_name, parameters=args, risk=tool_risk)
        result = await evaluator.evaluate(action)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_callbacks/test_risk_gate_factory.py -v`
Expected: ALL PASS (including existing tests — they don't use `action` param so `compound_name == tool_name`)

- [ ] **Step 5: Commit**

```bash
git add src/squire/callbacks/risk_gate.py tests/test_callbacks/test_risk_gate_factory.py
git commit -m "feat(risk): support compound tool:action names in risk gate"
```

---

## Task 2: docker_container Tool

Container lifecycle management: inspect, start, stop, restart, remove.

**Files:**
- Create: `src/squire/tools/docker_container.py`
- Test: `tests/test_tools/test_docker_container.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tools/test_docker_container.py`:

```python
"""Tests for docker_container tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_container import docker_container

from ..conftest import MockBackend, MockRegistry


@pytest.fixture
def container_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestInspect:
    @pytest.mark.asyncio
    async def test_inspect_returns_container_info(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Id": "abc123", "Name": "/nginx"}]', stderr=""),
        )
        result = await docker_container(action="inspect", container="nginx")
        assert "abc123" in result

    @pytest.mark.asyncio
    async def test_inspect_error(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="No such container: ghost"),
        )
        result = await docker_container(action="inspect", container="ghost")
        assert "Error" in result


class TestStart:
    @pytest.mark.asyncio
    async def test_start_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="start", container="nginx")
        assert "nginx" in result


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="stop", container="nginx")
        assert "nginx" in result


class TestRestart:
    @pytest.mark.asyncio
    async def test_restart_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="restart", container="nginx")
        assert "nginx" in result


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_container(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="remove", container="nginx")
        assert "nginx" in result

    @pytest.mark.asyncio
    async def test_remove_force(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="nginx\n", stderr=""),
        )
        result = await docker_container(action="remove", container="nginx", force=True)
        assert "nginx" in result

    @pytest.mark.asyncio
    async def test_remove_error_container_running(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="container is running"),
        )
        result = await docker_container(action="remove", container="nginx")
        assert "Error" in result


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_container(action="destroy", container="nginx")
        assert "Invalid action" in result

    @pytest.mark.asyncio
    async def test_container_required(self, mock_backend, container_registry):
        result = await docker_container(action="inspect", container="")
        assert "container name" in result.lower()


class TestHostResolution:
    @pytest.mark.asyncio
    async def test_explicit_host(self, mock_backend, container_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Id": "abc"}]', stderr=""),
        )
        result = await docker_container(action="inspect", container="nginx", host="remote-server")
        assert "abc" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools/test_docker_container.py -v`
Expected: FAIL — ImportError, module does not exist yet

- [ ] **Step 3: Implement docker_container tool**

Create `src/squire/tools/docker_container.py`:

```python
"""docker_container tool — manage individual container lifecycle."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_container:inspect": 1,
    "docker_container:start": 3,
    "docker_container:stop": 3,
    "docker_container:restart": 3,
    "docker_container:remove": 4,
}


async def docker_container(
    action: str,
    container: str,
    force: bool = False,
    host: str = "local",
) -> str:
    """Manage individual Docker container lifecycle.

    Args:
        action: The action to perform. One of:
            "inspect" - show detailed container configuration (read-only)
            "start" - start a stopped container
            "stop" - gracefully stop a running container
            "restart" - stop and start a container
            "remove" - delete a container (use force=True for running containers)
        container: Name or ID of the target container.
        force: Force the action (e.g., remove a running container). Default False.
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"inspect", "start", "stop", "restart", "remove"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    if not container:
        return "Error: container name is required."

    registry = get_registry()

    # Auto-resolve host from container/service name
    resolved_host = host
    if host == "local":
        matched = registry.resolve_host_for_service(container)
        if matched:
            resolved_host = matched

    backend = registry.get(resolved_host)

    if action == "inspect":
        cmd = ["docker", "inspect", container]
    elif action == "remove":
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container)
    else:
        cmd = ["docker", action, container]

    result = await backend.run(cmd, timeout=60.0)

    if result.returncode != 0:
        return f"Error running 'docker {action}' on '{container}': {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker {action} completed successfully for '{container}'."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools/test_docker_container.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/tools/docker_container.py tests/test_tools/test_docker_container.py
git commit -m "feat(tools): add docker_container tool for container lifecycle management"
```

---

## Task 3: docker_image Tool

Image management: list, inspect, pull, remove.

**Files:**
- Create: `src/squire/tools/docker_image.py`
- Test: `tests/test_tools/test_docker_image.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tools/test_docker_image.py`:

```python
"""Tests for docker_image tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_image import docker_image

from ..conftest import MockBackend, MockRegistry


@pytest.fixture
def image_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestList:
    @pytest.mark.asyncio
    async def test_list_images(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="REPOSITORY   TAG   IMAGE ID   SIZE\nnginx   latest   abc123   150MB\n",
                stderr="",
            ),
        )
        result = await docker_image(action="list")
        assert "nginx" in result

    @pytest.mark.asyncio
    async def test_list_empty(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="", stderr=""),
        )
        result = await docker_image(action="list")
        assert "no images" in result.lower() or "completed" in result.lower()


class TestInspect:
    @pytest.mark.asyncio
    async def test_inspect_image(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout='[{"Id": "sha256:abc123"}]', stderr=""),
        )
        result = await docker_image(action="inspect", image="nginx:latest")
        assert "abc123" in result

    @pytest.mark.asyncio
    async def test_inspect_missing_image_param(self, mock_backend, image_registry):
        result = await docker_image(action="inspect")
        assert "image" in result.lower()


class TestPull:
    @pytest.mark.asyncio
    async def test_pull_image(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="latest: Pulling from library/nginx\nDigest: sha256:abc\n", stderr=""),
        )
        result = await docker_image(action="pull", image="nginx:latest")
        assert "nginx" in result or "Pulling" in result

    @pytest.mark.asyncio
    async def test_pull_missing_image_param(self, mock_backend, image_registry):
        result = await docker_image(action="pull")
        assert "image" in result.lower()

    @pytest.mark.asyncio
    async def test_pull_error(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="pull access denied"),
        )
        result = await docker_image(action="pull", image="private/image")
        assert "Error" in result


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_image(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=0, stdout="Untagged: nginx:latest\nDeleted: sha256:abc\n", stderr=""),
        )
        result = await docker_image(action="remove", image="nginx:latest")
        assert "Untagged" in result or "Deleted" in result

    @pytest.mark.asyncio
    async def test_remove_image_in_use(self, mock_backend, image_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="image is being used by running container"),
        )
        result = await docker_image(action="remove", image="nginx:latest")
        assert "Error" in result


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_image(action="build")
        assert "Invalid action" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools/test_docker_image.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement docker_image tool**

Create `src/squire/tools/docker_image.py`:

```python
"""docker_image tool — manage Docker images."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_image:list": 1,
    "docker_image:inspect": 1,
    "docker_image:pull": 2,
    "docker_image:remove": 3,
}


async def docker_image(
    action: str = "list",
    image: str = "",
    host: str = "local",
) -> str:
    """Manage Docker images.

    Args:
        action: The action to perform. One of:
            "list" - list all images with repository, tag, and size (read-only)
            "inspect" - show detailed image metadata (read-only)
            "pull" - pull or update an image from a registry
            "remove" - remove an image (fails if in use by a running container)
        image: Image reference (e.g., "nginx:latest"). Required for inspect, pull, and remove.
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"list", "inspect", "pull", "remove"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    if action in {"inspect", "pull", "remove"} and not image:
        return f"Error: image reference is required for '{action}'."

    backend = get_registry().get(host)

    if action == "list":
        cmd = [
            "docker", "images",
            "--format", "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}",
        ]
    elif action == "inspect":
        cmd = ["docker", "image", "inspect", image]
    elif action == "pull":
        cmd = ["docker", "pull", image]
    elif action == "remove":
        cmd = ["docker", "rmi", image]

    result = await backend.run(cmd, timeout=120.0)

    if result.returncode != 0:
        return f"Error running 'docker image {action}'{f' for {image!r}' if image else ''}: {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker image {action} completed successfully."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools/test_docker_image.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/tools/docker_image.py tests/test_tools/test_docker_image.py
git commit -m "feat(tools): add docker_image tool for image management"
```

---

## Task 4: docker_cleanup Tool

Pruning and resource recovery: df, prune_containers, prune_images, prune_volumes, prune_all.

**Files:**
- Create: `src/squire/tools/docker_cleanup.py`
- Test: `tests/test_tools/test_docker_cleanup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tools/test_docker_cleanup.py`:

```python
"""Tests for docker_cleanup tool with mocked backend."""

import pytest

from squire.system.backend import CommandResult
from squire.tools.docker_cleanup import docker_cleanup

from ..conftest import MockBackend, MockRegistry


@pytest.fixture
def cleanup_registry(mock_backend):
    from squire.tools._registry import set_registry

    registry = MockRegistry(mock_backend)
    set_registry(registry)
    yield registry
    set_registry(None)


class TestDf:
    @pytest.mark.asyncio
    async def test_disk_usage(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="TYPE    TOTAL   ACTIVE  SIZE    RECLAIMABLE\nImages  5       2       1.2GB   800MB (66%)\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="df")
        assert "Images" in result


class TestPruneContainers:
    @pytest.mark.asyncio
    async def test_prune_containers(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Containers:\nabc123\ndef456\n\nTotal reclaimed space: 50MB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_containers")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestPruneImages:
    @pytest.mark.asyncio
    async def test_prune_images(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Images:\nsha256:abc123\n\nTotal reclaimed space: 500MB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_images")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestPruneVolumes:
    @pytest.mark.asyncio
    async def test_prune_volumes(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Volumes:\nvol1\n\nTotal reclaimed space: 1GB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_volumes")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestPruneAll:
    @pytest.mark.asyncio
    async def test_prune_all(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(
                returncode=0,
                stdout="Deleted Containers:\nabc\nDeleted Images:\nsha256:def\n\nTotal reclaimed space: 2GB\n",
                stderr="",
            ),
        )
        result = await docker_cleanup(action="prune_all")
        assert "reclaimed" in result.lower() or "Deleted" in result


class TestErrors:
    @pytest.mark.asyncio
    async def test_prune_error(self, mock_backend, cleanup_registry):
        mock_backend.set_response(
            "docker",
            CommandResult(returncode=1, stdout="", stderr="permission denied"),
        )
        result = await docker_cleanup(action="prune_containers")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        result = await docker_cleanup(action="nuke")
        assert "Invalid action" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools/test_docker_cleanup.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement docker_cleanup tool**

Create `src/squire/tools/docker_cleanup.py`:

```python
"""docker_cleanup tool — prune unused Docker resources."""

from ._registry import get_registry

RISK_LEVELS: dict[str, int] = {
    "docker_cleanup:df": 1,
    "docker_cleanup:prune_containers": 3,
    "docker_cleanup:prune_images": 3,
    "docker_cleanup:prune_volumes": 4,
    "docker_cleanup:prune_all": 4,
}


async def docker_cleanup(
    action: str = "df",
    host: str = "local",
) -> str:
    """Prune unused Docker resources and check disk usage.

    Args:
        action: The cleanup action to perform. One of:
            "df" - show Docker disk usage breakdown (read-only)
            "prune_containers" - remove all stopped containers
            "prune_images" - remove dangling (unused) images
            "prune_volumes" - remove unused volumes (WARNING: may delete data)
            "prune_all" - system prune: containers, images, and networks (excludes volumes)
        host: Target host name (default "local").

    Returns the command output as text.
    """
    allowed_actions = {"df", "prune_containers", "prune_images", "prune_volumes", "prune_all"}
    if action not in allowed_actions:
        return f"Invalid action '{action}'. Allowed: {', '.join(sorted(allowed_actions))}"

    backend = get_registry().get(host)

    if action == "df":
        cmd = ["docker", "system", "df"]
    elif action == "prune_containers":
        cmd = ["docker", "container", "prune", "-f"]
    elif action == "prune_images":
        cmd = ["docker", "image", "prune", "-f"]
    elif action == "prune_volumes":
        cmd = ["docker", "volume", "prune", "-f"]
    elif action == "prune_all":
        cmd = ["docker", "system", "prune", "-f"]

    result = await backend.run(cmd, timeout=120.0)

    if result.returncode != 0:
        return f"Error running 'docker {action}': {result.stderr}"

    output = result.stdout.strip()
    return output if output else f"docker {action} completed successfully."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools/test_docker_cleanup.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/tools/docker_cleanup.py tests/test_tools/test_docker_cleanup.py
git commit -m "feat(tools): add docker_cleanup tool for pruning and resource recovery"
```

---

## Task 5: Tool Registration and Agent Integration

Register all three new tools in the tool registry, add them to the Container agent's tool group, and update the Container agent instructions.

**Files:**
- Modify: `src/squire/tools/__init__.py:16-64`
- Modify: `src/squire/tools/groups.py:1-38`
- Modify: `src/squire/instructions/container_agent.py:26-40`

- [ ] **Step 1: Update `src/squire/tools/__init__.py`**

Add imports for the three new tool modules after line 28 (after the `docker_ps` import block):

```python
from .docker_cleanup import RISK_LEVELS as _dclean_risks
from .docker_cleanup import docker_cleanup
from .docker_container import RISK_LEVELS as _dcont_risks
from .docker_container import docker_container
from .docker_image import RISK_LEVELS as _dimg_risks
from .docker_image import docker_image
```

Add to `ALL_TOOLS` list (after `safe_tool(docker_compose)`):

```python
    safe_tool(docker_container),
    safe_tool(docker_image),
    safe_tool(docker_cleanup),
```

Add to `TOOL_RISK_LEVELS` dict (after the `docker_compose` entry):

```python
    **_dcont_risks,
    **_dimg_risks,
    **_dclean_risks,
```

- [ ] **Step 2: Update `src/squire/tools/groups.py`**

Add imports for the three new tools:

```python
from .docker_cleanup import docker_cleanup
from .docker_container import docker_container
from .docker_image import docker_image
```

Update `CONTAINER_TOOLS` at line 31 to include new tools:

```python
CONTAINER_TOOLS = [
    safe_tool(docker_logs),
    safe_tool(docker_compose),
    safe_tool(docker_container),
    safe_tool(docker_image),
    safe_tool(docker_cleanup),
]
```

- [ ] **Step 3: Update container agent instructions**

In `src/squire/instructions/container_agent.py`, replace the role and tool usage sections (lines 26-40) with:

```python
## Your Role: Container Manager
You manage container lifecycle — viewing logs, managing containers, pulling
images, cleaning up resources, and managing Docker Compose stacks. Your tools
can modify container state, so always explain what you'll do and why before
executing mutations.

## Tool Usage
- Use `docker_logs` to view container logs for troubleshooting.
- Use `docker_compose` to manage Compose stacks (start, stop, restart, pull, up, down).
- Use `docker_container` to manage individual containers (inspect, start, stop, restart, remove).
- Use `docker_image` to manage images (list, inspect, pull, remove).
- Use `docker_cleanup` to check disk usage and prune unused resources (containers, images, volumes).
- When using `docker_compose`, provide the service name — the project
  directory resolves automatically from the host's service_root.
- For destructive actions (remove, prune), explain what you'll do and the
  impact before executing. Volume pruning can cause data loss.
- If a tool call is blocked by the risk profile, tell the user and suggest
  alternatives if possible.
- NEVER fabricate command output. If a tool fails, report the error.
```

- [ ] **Step 4: Run full test suite to verify nothing broke**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/tools/__init__.py src/squire/tools/groups.py src/squire/instructions/container_agent.py
git commit -m "feat(agents): register container lifecycle tools and update agent instructions"
```

---

## Task 6: CHANGELOG Update

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add changelog entry under Unreleased**

Add the following under the `## [Unreleased]` section in `CHANGELOG.md`:

```markdown
### Added
- **Container lifecycle tools** — three new consolidated tools for full container management:
  - `docker_container` — manage individual containers (inspect, start, stop, restart, remove)
  - `docker_image` — manage images (list, inspect, pull, remove)
  - `docker_cleanup` — prune resources and check disk usage (df, prune_containers, prune_images, prune_volumes, prune_all)
- **Compound action risk evaluation** — risk gate now constructs `tool:action` names for per-action risk levels, enabling fine-grained guardrails configuration (e.g., `tools_deny = ["docker_cleanup:prune_volumes"]`)
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add container lifecycle tools to changelog"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run the full CI check**

Run: `make ci`
Expected: Lint, format check, and all tests pass.

- [ ] **Step 2: Verify tool count**

Run: `uv run python -c "from squire.tools import ALL_TOOLS, TOOL_RISK_LEVELS; print(f'Tools: {len(ALL_TOOLS)}'); print(f'Risk entries: {len(TOOL_RISK_LEVELS)}')"`
Expected: Tools: 12, Risk entries: 23 (9 original + 5 container + 4 image + 5 cleanup)

- [ ] **Step 3: Verify compound risk gate**

Run: `uv run python -c "from squire.tools import TOOL_RISK_LEVELS; [print(f'{k}: {v}') for k, v in sorted(TOOL_RISK_LEVELS.items()) if ':' in k]"`
Expected: All 14 compound entries printed with correct risk levels.
