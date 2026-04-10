# Tools Visibility & Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/tools` page to the web UI that lets users view all tools with metadata and configure per-tool policies (enable/disable, risk overrides, approval policy).

**Architecture:** New `GET /api/tools` endpoint introspects the tool registry and merges guardrails config. Frontend `/tools` page renders a table with collapsible multi-action rows and inline config controls. Config changes go through the existing `PATCH /api/config/guardrails` endpoint. Risk gate reads a new `tools_risk_overrides` dict to substitute base risk levels.

**Tech Stack:** Python (FastAPI, Pydantic), TypeScript (Next.js, React, shadcn/ui, SWR), pytest

---

## File Structure

### Files to Create
| File | Responsibility |
|---|---|
| `src/squire/api/routers/tools.py` | `GET /api/tools` endpoint — introspects tool registry, merges guardrails |
| `web/src/app/tools/page.tsx` | Tools catalog page — table, collapsible rows, inline config |
| `tests/test_api/__init__.py` | Test package init |
| `tests/test_api/test_tools_endpoint.py` | Tests for `GET /api/tools` and guardrails merge |

### Files to Modify
| File | Change |
|---|---|
| `src/squire/config/guardrails.py:44-56` | Add `tools_risk_overrides` field |
| `src/squire/api/schemas.py:221-231` | Add `tools_risk_overrides` to `GuardrailsConfigUpdate`; add `ToolParameter`, `ToolAction`, `ToolInfo` models |
| `src/squire/callbacks/risk_gate.py:33-151` | Accept + apply `risk_overrides` parameter |
| `src/squire/api/app.py:164-174` | Register tools router |
| `src/squire/api/routers/chat.py:165-169` | Pass `risk_overrides` to `create_risk_gate` |
| `src/squire/api/routers/chat.py:183-186` | Pass `risk_overrides` to `create_risk_gate` (single-agent path) |
| *(obsolete)* | Previously `main.py` wired `risk_overrides` into `create_risk_gate` for the removed terminal chat path; web chat lives in `api/routers/chat.py`. |
| `src/squire/watch.py:163-168` | Pass `risk_overrides` to `create_risk_gate` (watch mode factory) |
| `src/squire/watch.py:180` | Pass `risk_overrides` to `create_risk_gate` (watch single-agent path) |
| `web/src/lib/types.ts` | Add `ToolParameter`, `ToolAction`, `ToolInfo` types |
| `web/src/components/layout/sidebar.tsx:6-14,25-29` | Add Wrench icon and Tools nav entry |
| `tests/test_callbacks/test_risk_gate_factory.py` | Add risk override tests |
| `CHANGELOG.md:9` | Add entry under `[Unreleased]` |

---

### Task 1: Add `tools_risk_overrides` to GuardrailsConfig

**Files:**
- Modify: `src/squire/config/guardrails.py:44-56`
- Modify: `src/squire/api/schemas.py:221-231`

- [ ] **Step 1: Add `tools_risk_overrides` field to GuardrailsConfig**

In `src/squire/config/guardrails.py`, add after the `tools_deny` field (after line 56):

```python
    tools_risk_overrides: dict[str, int] = Field(
        default_factory=dict,
        description="Per-tool risk level overrides (tool name or tool:action -> 1-5)",
    )
```

- [ ] **Step 2: Add `tools_risk_overrides` to GuardrailsConfigUpdate**

In `src/squire/api/schemas.py`, add after the `tools_deny` field in `GuardrailsConfigUpdate` (after line 224):

```python
    tools_risk_overrides: dict[str, int] | None = None
```

- [ ] **Step 3: Verify config loads correctly**

Run: `uv run python -c "from squire.config import GuardrailsConfig; g = GuardrailsConfig(); print(g.tools_risk_overrides)"`
Expected: `{}`

- [ ] **Step 4: Commit**

```bash
git add src/squire/config/guardrails.py src/squire/api/schemas.py
git commit -m "feat(config): add tools_risk_overrides to GuardrailsConfig"
```

---

### Task 2: Add Pydantic schemas for ToolInfo

**Files:**
- Modify: `src/squire/api/schemas.py`

- [ ] **Step 1: Add ToolParameter, ToolAction, and ToolInfo models**

In `src/squire/api/schemas.py`, add before the `ConfigResponse` class (before line 169):

```python
# --- Tools ---


class ToolParameter(BaseModel):
    name: str
    type: str
    required: bool = True
    default: str | None = None


class ToolAction(BaseModel):
    name: str
    risk_level: int
    risk_override: int | None = None


class ToolInfo(BaseModel):
    name: str
    description: str
    group: str
    parameters: list[ToolParameter]
    actions: list[ToolAction] | None = None
    risk_level: int | None = None  # single-action tools only
    risk_override: int | None = None  # single-action tools only
    status: str  # "enabled" | "disabled"
    approval_policy: str | None = None  # "always" | "never" | null
```

- [ ] **Step 2: Verify models instantiate correctly**

Run: `uv run python -c "from squire.api.schemas import ToolInfo, ToolParameter; t = ToolInfo(name='test', description='d', group='monitor', parameters=[ToolParameter(name='host', type='str', required=False, default='local')], status='enabled'); print(t.model_dump_json(indent=2))"`
Expected: JSON output with all fields

- [ ] **Step 3: Commit**

```bash
git add src/squire/api/schemas.py
git commit -m "feat(schemas): add ToolParameter, ToolAction, ToolInfo models"
```

---

### Task 3: Create `GET /api/tools` endpoint

**Files:**
- Create: `src/squire/api/routers/tools.py`
- Modify: `src/squire/api/app.py:34,165-174`

- [ ] **Step 1: Write the test file**

Create `tests/test_api/__init__.py` (empty) and `tests/test_api/test_tools_endpoint.py`:

```python
"""Tests for the GET /api/tools endpoint."""

import pytest

from squire.api.routers.tools import _build_tool_catalog
from squire.config import GuardrailsConfig


class TestBuildToolCatalog:
    def test_returns_all_tools(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        names = {t.name for t in tools}
        assert "system_info" in names
        assert "docker_container" in names
        assert "run_command" in names
        assert len(tools) == 12  # all 12 registered tools

    def test_single_action_tool_has_risk_level(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.risk_level == 1
        assert si.actions is None
        assert si.risk_override is None

    def test_multi_action_tool_has_actions(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        dc = next(t for t in tools if t.name == "docker_container")
        assert dc.actions is not None
        assert dc.risk_level is None  # multi-action: risk is on actions
        action_names = {a.name for a in dc.actions}
        assert action_names == {"inspect", "start", "stop", "restart", "remove"}
        inspect_action = next(a for a in dc.actions if a.name == "inspect")
        assert inspect_action.risk_level == 1
        remove_action = next(a for a in dc.actions if a.name == "remove")
        assert remove_action.risk_level == 4

    def test_tool_groups_assigned(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        groups = {t.name: t.group for t in tools}
        assert groups["system_info"] == "monitor"
        assert groups["docker_container"] == "container"
        assert groups["run_command"] == "admin"

    def test_parameters_extracted(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        param_names = {p.name for p in si.parameters}
        assert "host" in param_names
        host_param = next(p for p in si.parameters if p.name == "host")
        assert host_param.required is False
        assert host_param.default == "local"

    def test_denied_tool_shows_disabled(self):
        guardrails = GuardrailsConfig(tools_deny=["run_command"])
        tools = _build_tool_catalog(guardrails)
        rc = next(t for t in tools if t.name == "run_command")
        assert rc.status == "disabled"

    def test_approval_policy_always(self):
        guardrails = GuardrailsConfig(tools_require_approval=["run_command"])
        tools = _build_tool_catalog(guardrails)
        rc = next(t for t in tools if t.name == "run_command")
        assert rc.approval_policy == "always"

    def test_approval_policy_never(self):
        guardrails = GuardrailsConfig(tools_allow=["system_info"])
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.approval_policy == "never"

    def test_risk_override_single_action(self):
        guardrails = GuardrailsConfig(tools_risk_overrides={"system_info": 3})
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.risk_level == 1  # base unchanged
        assert si.risk_override == 3

    def test_risk_override_multi_action(self):
        guardrails = GuardrailsConfig(tools_risk_overrides={"docker_container:remove": 5})
        tools = _build_tool_catalog(guardrails)
        dc = next(t for t in tools if t.name == "docker_container")
        remove = next(a for a in dc.actions if a.name == "remove")
        assert remove.risk_level == 4  # base unchanged
        assert remove.risk_override == 5
        # Other actions should not have override
        inspect_action = next(a for a in dc.actions if a.name == "inspect")
        assert inspect_action.risk_override is None

    def test_default_approval_is_none(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert si.approval_policy is None

    def test_description_is_first_line(self):
        guardrails = GuardrailsConfig()
        tools = _build_tool_catalog(guardrails)
        si = next(t for t in tools if t.name == "system_info")
        assert "system information" in si.description.lower()
        assert "\n" not in si.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api/test_tools_endpoint.py -v`
Expected: FAIL — `_build_tool_catalog` not found

- [ ] **Step 3: Create the tools router**

Create `src/squire/api/routers/tools.py`:

```python
"""Tool catalog endpoint — introspects the tool registry and merges guardrails."""

import inspect

from fastapi import APIRouter, Depends

from ...config import GuardrailsConfig
from ...tools import TOOL_RISK_LEVELS
from ...tools.groups import ADMIN_TOOL_NAMES, CONTAINER_TOOL_NAMES, MONITOR_TOOL_NAMES
from ..dependencies import get_guardrails
from ..schemas import ToolAction, ToolInfo, ToolParameter

# Import raw tool functions for signature introspection
from ...tools.docker_cleanup import docker_cleanup
from ...tools.docker_compose import docker_compose
from ...tools.docker_container import docker_container
from ...tools.docker_image import docker_image
from ...tools.docker_logs import docker_logs
from ...tools.docker_ps import docker_ps
from ...tools.journalctl import journalctl
from ...tools.network_info import network_info
from ...tools.read_config import read_config
from ...tools.run_command import run_command
from ...tools.system_info import system_info
from ...tools.systemctl import systemctl

router = APIRouter()

# Ordered list of (name, function) for deterministic output
_TOOL_ENTRIES: list[tuple[str, object]] = [
    ("system_info", system_info),
    ("network_info", network_info),
    ("docker_ps", docker_ps),
    ("docker_logs", docker_logs),
    ("docker_compose", docker_compose),
    ("docker_container", docker_container),
    ("docker_image", docker_image),
    ("docker_cleanup", docker_cleanup),
    ("read_config", read_config),
    ("journalctl", journalctl),
    ("systemctl", systemctl),
    ("run_command", run_command),
]


def _get_group(tool_name: str) -> str:
    """Map a tool name to its agent group."""
    if tool_name in MONITOR_TOOL_NAMES:
        return "monitor"
    if tool_name in CONTAINER_TOOL_NAMES:
        return "container"
    if tool_name in ADMIN_TOOL_NAMES:
        return "admin"
    return "other"


def _extract_parameters(func: object) -> list[ToolParameter]:
    """Extract parameter metadata from a tool function's signature."""
    sig = inspect.signature(func)
    params = []
    for name, param in sig.parameters.items():
        hint = param.annotation
        if hint is inspect.Parameter.empty:
            type_name = "str"
        elif hasattr(hint, "__name__"):
            type_name = hint.__name__
        else:
            type_name = str(hint).replace("typing.", "")
        params.append(
            ToolParameter(
                name=name,
                type=type_name,
                required=param.default is inspect.Parameter.empty,
                default=str(param.default) if param.default is not inspect.Parameter.empty else None,
            )
        )
    return params


def _get_action_names(tool_name: str) -> list[str]:
    """Return action names for a multi-action tool, or empty list for single-action."""
    prefix = f"{tool_name}:"
    return [key.split(":", 1)[1] for key in TOOL_RISK_LEVELS if key.startswith(prefix)]


def _build_tool_catalog(guardrails: GuardrailsConfig) -> list[ToolInfo]:
    """Build the full tool catalog, merging registry data with guardrails config."""
    tools: list[ToolInfo] = []
    denied = set(guardrails.tools_deny)
    allowed = set(guardrails.tools_allow)
    require_approval = set(guardrails.tools_require_approval)
    overrides = guardrails.tools_risk_overrides

    for name, func in _TOOL_ENTRIES:
        params = _extract_parameters(func)
        description = func.__doc__.strip().split("\n")[0] if func.__doc__ else ""
        group = _get_group(name)
        status = "disabled" if name in denied else "enabled"

        # Determine approval policy
        approval_policy: str | None = None
        if name in require_approval:
            approval_policy = "always"
        elif name in allowed:
            approval_policy = "never"

        action_names = _get_action_names(name)

        if action_names:
            actions = [
                ToolAction(
                    name=action,
                    risk_level=TOOL_RISK_LEVELS.get(f"{name}:{action}", 1),
                    risk_override=overrides.get(f"{name}:{action}"),
                )
                for action in action_names
            ]
            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    group=group,
                    parameters=params,
                    actions=actions,
                    status=status,
                    approval_policy=approval_policy,
                )
            )
        else:
            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    group=group,
                    parameters=params,
                    risk_level=TOOL_RISK_LEVELS.get(name, 1),
                    risk_override=overrides.get(name),
                    status=status,
                    approval_policy=approval_policy,
                )
            )
    return tools


@router.get("", response_model=list[ToolInfo])
def list_tools(guardrails: GuardrailsConfig = Depends(get_guardrails)):
    """List all available tools with their metadata and effective configuration."""
    return _build_tool_catalog(guardrails)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api/test_tools_endpoint.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Register the router in the app**

In `src/squire/api/app.py`, add the import (line 34):

```python
from .routers import alerts, chat, config, events, hosts, notifications, sessions, skills, system, tools, watch
```

Then add the router mount (after the skills router, around line 171):

```python
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_api/ src/squire/api/routers/tools.py src/squire/api/app.py
git commit -m "feat(api): add GET /api/tools catalog endpoint"
```

---

### Task 4: Update risk gate to apply `tools_risk_overrides`

**Files:**
- Modify: `src/squire/callbacks/risk_gate.py:33-86`
- Modify: `tests/test_callbacks/test_risk_gate_factory.py`

- [ ] **Step 1: Write failing tests for risk overrides**

Append to `tests/test_callbacks/test_risk_gate_factory.py`:

```python
class TestRiskOverrides:
    @pytest.mark.asyncio
    async def test_override_lowers_risk(self):
        """A risk override should substitute the base risk level."""
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            risk_overrides={"run_command": 1},
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=3))
        assert result is None  # risk 1 <= threshold 3

    @pytest.mark.asyncio
    async def test_override_raises_risk(self):
        """A risk override can raise the risk above threshold."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
            risk_overrides={"system_info": 5},
        )
        result = await gate(_make_tool("system_info"), {}, _make_context(threshold=3))
        assert result is not None  # risk 5 > threshold 3

    @pytest.mark.asyncio
    async def test_override_compound_action(self):
        """Risk overrides work with compound action names."""
        gate = create_risk_gate(
            tool_risk_levels={"docker_container:remove": 4},
            risk_overrides={"docker_container:remove": 1},
        )
        result = await gate(
            _make_tool("docker_container"),
            {"action": "remove"},
            _make_context(threshold=3),
        )
        assert result is None  # overridden to risk 1

    @pytest.mark.asyncio
    async def test_override_only_affects_specified_tool(self):
        """An override for one tool should not affect another."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1, "run_command": 5},
            risk_overrides={"run_command": 1},
        )
        # system_info should still use its base risk of 1
        result = await gate(_make_tool("system_info"), {}, _make_context(threshold=3))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_overrides_is_default_behavior(self):
        """When risk_overrides is None/empty, behavior is unchanged."""
        gate = create_risk_gate(
            tool_risk_levels={"run_command": 5},
            risk_overrides={},
        )
        result = await gate(_make_tool("run_command"), {"command": "ls"}, _make_context(threshold=3))
        assert result is not None  # risk 5 > threshold 3

    @pytest.mark.asyncio
    async def test_remote_host_still_bumps_after_override(self):
        """Remote host escalation should apply on top of the override."""
        gate = create_risk_gate(
            tool_risk_levels={"system_info": 1},
            risk_overrides={"system_info": 3},
        )
        # Override to 3, remote bump to 4, threshold 3 → needs approval
        result = await gate(
            _make_tool("system_info"),
            {"host": "remote-server"},
            _make_context(threshold=3),
        )
        assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_callbacks/test_risk_gate_factory.py::TestRiskOverrides -v`
Expected: FAIL — `risk_overrides` is not a valid parameter

- [ ] **Step 3: Add `risk_overrides` parameter to `create_risk_gate`**

In `src/squire/callbacks/risk_gate.py`, update the function signature (line 33) to add the new parameter:

```python
def create_risk_gate(
    tool_risk_levels: dict[str, int] | None = None,
    risk_overrides: dict[str, int] | None = None,
    approval_provider: ApprovalProvider | None = None,
    default_threshold: int | None = None,
    headless: bool = False,
    notifier: Any | None = None,
) -> BeforeToolCallback:
```

Update the docstring to include:

```
        risk_overrides: Per-tool risk level overrides from guardrails config.
            Keys are tool names or tool:action compound names. When set,
            these substitute the base risk level from tool_risk_levels.
```

After line 57 (`scoped_risk_levels = tool_risk_levels or TOOL_RISK_LEVELS`), add:

```python
    _overrides = risk_overrides or {}
```

After line 86 (`tool_risk = scoped_risk_levels[compound_name]`), add the override logic:

```python
        # Apply per-tool risk override if configured
        if compound_name in _overrides:
            tool_risk = _overrides[compound_name]
        elif tool_name in _overrides:
            tool_risk = _overrides[tool_name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_callbacks/test_risk_gate_factory.py -v`
Expected: All tests PASS (existing + new override tests)

- [ ] **Step 5: Commit**

```bash
git add src/squire/callbacks/risk_gate.py tests/test_callbacks/test_risk_gate_factory.py
git commit -m "feat(risk-gate): apply tools_risk_overrides in risk evaluation"
```

---

### Task 5: Wire `risk_overrides` into all call sites

**Files:**
- Modify: `src/squire/api/routers/chat.py:165-169,183-186`
- Modify: `src/squire/main.py:158-162,171-173`
- Modify: `src/squire/watch.py:163-168,180`

- [ ] **Step 1: Update chat.py — multi-agent factory (line 165-169)**

In `src/squire/api/routers/chat.py`, update `_make_risk_gate`:

```python
    def _make_risk_gate(tool_risk_levels: dict[str, int]):
        guardrails = GuardrailsConfig()
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            risk_overrides=dict(guardrails.tools_risk_overrides),
            approval_provider=approval_bridge,
        )
```

Add the import at the top of the file if `GuardrailsConfig` is not already imported (it is imported at line 200 inside the function — use the same import):

The `GuardrailsConfig` import already exists in the function scope. Since `_make_risk_gate` is defined before the guardrails loading block, load it fresh inside the factory so it picks up runtime changes.

- [ ] **Step 2: Update chat.py — single-agent path (line 183-186)**

```python
        guardrails_for_gate = GuardrailsConfig()
        risk_gate_callback = create_risk_gate(
            tool_risk_levels=TOOL_RISK_LEVELS,
            risk_overrides=dict(guardrails_for_gate.tools_risk_overrides),
            approval_provider=approval_bridge,
        )
```

Note: `GuardrailsConfig` is already imported later in the function. Move or add an early import. Actually, looking at the code, `GuardrailsConfig` is used on line 200 already. Just use it earlier; it's imported at the module level via `from squire.config import ... GuardrailsConfig` — check the chat.py imports and add if needed.

- [ ] **Step 3: Update main.py — multi-agent factory (line 158-162)**

In `src/squire/main.py`, update `_make_risk_gate`:

```python
    def _make_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            risk_overrides=dict(guardrails.tools_risk_overrides),
            approval_provider=approval_bridge,
        )
```

Note: `guardrails` is loaded at line 184, which is after `_make_risk_gate` is defined but before it's called (it's a closure — it captures `guardrails` lazily). However, `guardrails` is defined _after_ the function. This won't work because the function is called during `create_squire_agent` at line 165, before `guardrails` is assigned at line 184.

Fix: move the guardrails loading before the agent creation. Move line 184 (`guardrails = GuardrailsConfig()`) to before line 157 (before the `_make_risk_gate` definition):

```python
    # Build the risk evaluation pipeline
    guardrails = GuardrailsConfig()

    # Build the approval provider
    approval_bridge = ApprovalBridge()

    # Build the agent — multi-agent mode uses a factory for per-agent risk gates
    def _make_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            risk_overrides=dict(guardrails.tools_risk_overrides),
            approval_provider=approval_bridge,
        )
```

And remove the later duplicate `guardrails = GuardrailsConfig()` at line 184.

- [ ] **Step 4: Update main.py — single-agent path (line 171-173)**

```python
        risk_gate_callback = create_risk_gate(
            tool_risk_levels=TOOL_RISK_LEVELS,
            risk_overrides=dict(guardrails.tools_risk_overrides),
            approval_provider=approval_bridge,
        )
```

- [ ] **Step 5: Update watch.py — multi-agent factory (line 163-168)**

In `src/squire/watch.py`, update `_make_headless_risk_gate`:

```python
    def _make_headless_risk_gate(tool_risk_levels: dict[str, int]):
        return create_risk_gate(
            tool_risk_levels=tool_risk_levels,
            risk_overrides=dict(guardrails.tools_risk_overrides),
            headless=True,
            notifier=block_notifier,
        )
```

`guardrails` is already loaded at line 149, so the closure can capture it.

- [ ] **Step 6: Update watch.py — single-agent path (line 180)**

```python
        agent = create_squire_agent(
            app_config=app_config,
            llm_config=llm_config,
            before_tool_callback=_make_headless_risk_gate(TOOL_RISK_LEVELS),
        )
```

This already calls the factory, so no change needed — the factory already includes the overrides from step 5.

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/squire/api/routers/chat.py src/squire/main.py src/squire/watch.py
git commit -m "feat(risk-gate): wire tools_risk_overrides into all risk gate call sites"
```

---

### Task 6: Add TypeScript types and sidebar nav entry

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/components/layout/sidebar.tsx`

- [ ] **Step 1: Add TypeScript types**

In `web/src/lib/types.ts`, add before the `ConfigResponse` interface (before line 169):

```typescript
// --- Tools ---

export interface ToolParameter {
  name: string;
  type: string;
  required: boolean;
  default?: string | null;
}

export interface ToolAction {
  name: string;
  risk_level: number;
  risk_override: number | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  group: string;
  parameters: ToolParameter[];
  actions: ToolAction[] | null;
  risk_level: number | null;
  risk_override: number | null;
  status: "enabled" | "disabled";
  approval_policy: "always" | "never" | null;
}
```

- [ ] **Step 2: Add sidebar nav entry**

In `web/src/components/layout/sidebar.tsx`, add `Wrench` to the lucide-react import (line 6):

```typescript
import {
  MessageSquare,
  Server,
  Bell,
  Settings,
  Activity,
  History,
  ListChecks,
  Eye,
  Wrench,
} from "lucide-react";
```

Add the Tools entry to `systemNav` (line 25), before Hosts:

```typescript
const systemNav = [
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/hosts", label: "Hosts", icon: Server },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/config", label: "Config", icon: Settings },
];
```

- [ ] **Step 3: Verify the frontend builds**

Run: `cd web && npm run build`
Expected: Build succeeds (new types are valid, sidebar compiles)

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/types.ts web/src/components/layout/sidebar.tsx
git commit -m "feat(web): add ToolInfo types and Tools sidebar entry"
```

---

### Task 7: Create the `/tools` page

**Files:**
- Create: `web/src/app/tools/page.tsx`

- [ ] **Step 1: Create the tools page**

Create `web/src/app/tools/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPatch } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Wrench, ChevronRight, Save, Loader2 } from "lucide-react";
import type { ToolInfo, ToolAction } from "@/lib/types";

const RISK_COLORS: Record<number, string> = {
  1: "bg-green-500/15 text-green-700 dark:text-green-400",
  2: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  3: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  4: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  5: "bg-red-500/15 text-red-700 dark:text-red-400",
};

const GROUP_COLORS: Record<string, string> = {
  monitor: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  container: "bg-purple-500/15 text-purple-700 dark:text-purple-400",
  admin: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
};

function RiskBadge({ level, override }: { level: number; override?: number | null }) {
  const effective = override ?? level;
  return (
    <Badge variant="outline" className={RISK_COLORS[effective] ?? ""}>
      {effective}
      {override != null && <span className="ml-1 opacity-60">(was {level})</span>}
    </Badge>
  );
}

function ApprovalBadge({ policy }: { policy: string | null }) {
  if (policy === "always") return <Badge variant="secondary">Always</Badge>;
  if (policy === "never") return <Badge variant="outline">Auto-allow</Badge>;
  return <Badge variant="outline" className="text-muted-foreground">Risk-based</Badge>;
}

function ActionRow({ toolName, action, onOverride }: {
  toolName: string;
  action: ToolAction;
  onOverride: (compound: string, value: number | null) => void;
}) {
  const compound = `${toolName}:${action.name}`;
  return (
    <TableRow className="bg-muted/30">
      <TableCell className="pl-10 text-sm text-muted-foreground">{action.name}</TableCell>
      <TableCell />
      <TableCell>
        <RiskBadge level={action.risk_level} override={action.risk_override} />
      </TableCell>
      <TableCell />
      <TableCell />
      <TableCell>
        <Input
          type="number"
          min={1}
          max={5}
          className="w-16 h-7 text-xs"
          placeholder="-"
          value={action.risk_override ?? ""}
          onChange={(e) => {
            const v = e.target.value ? parseInt(e.target.value, 10) : null;
            if (v !== null && (v < 1 || v > 5)) return;
            onOverride(compound, v);
          }}
        />
      </TableCell>
    </TableRow>
  );
}

export default function ToolsPage() {
  const { data: tools, mutate } = useSWR("/api/tools", () =>
    apiGet<ToolInfo[]>("/api/tools")
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [persist, setPersist] = useState(false);

  // Track pending config changes
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, number | null>>({});
  const [pendingDeny, setPendingDeny] = useState<Set<string> | null>(null);
  const [pendingApproval, setPendingApproval] = useState<Record<string, string | null>>({});

  const hasPending =
    Object.keys(pendingOverrides).length > 0 ||
    pendingDeny !== null ||
    Object.keys(pendingApproval).length > 0;

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const getEffectiveStatus = (tool: ToolInfo): boolean => {
    if (pendingDeny !== null) return !pendingDeny.has(tool.name);
    return tool.status === "enabled";
  };

  const getEffectiveApproval = (tool: ToolInfo): string | null => {
    if (tool.name in pendingApproval) return pendingApproval[tool.name];
    return tool.approval_policy;
  };

  const handleToggleStatus = (tool: ToolInfo) => {
    const currentDeny = pendingDeny ?? new Set(
      tools?.filter((t) => t.status === "disabled").map((t) => t.name) ?? []
    );
    const next = new Set(currentDeny);
    if (next.has(tool.name)) next.delete(tool.name);
    else next.add(tool.name);
    setPendingDeny(next);
  };

  const handleApprovalChange = (toolName: string, value: string) => {
    setPendingApproval((prev) => ({
      ...prev,
      [toolName]: value === "default" ? null : value,
    }));
  };

  const handleOverride = (compound: string, value: number | null) => {
    setPendingOverrides((prev) => ({ ...prev, [compound]: value }));
  };

  const handleSave = async () => {
    if (!tools) return;
    setSaving(true);
    try {
      const patch: Record<string, unknown> = {};

      // Build tools_deny from pending
      if (pendingDeny !== null) {
        patch.tools_deny = Array.from(pendingDeny);
      }

      // Build approval lists from pending
      if (Object.keys(pendingApproval).length > 0) {
        // Start from current state
        const currentAllow = new Set(
          tools.filter((t) => t.approval_policy === "never").map((t) => t.name)
        );
        const currentRequire = new Set(
          tools.filter((t) => t.approval_policy === "always").map((t) => t.name)
        );

        for (const [name, policy] of Object.entries(pendingApproval)) {
          currentAllow.delete(name);
          currentRequire.delete(name);
          if (policy === "never") currentAllow.add(name);
          else if (policy === "always") currentRequire.add(name);
        }

        patch.tools_allow = Array.from(currentAllow);
        patch.tools_require_approval = Array.from(currentRequire);
      }

      // Build risk overrides from pending
      if (Object.keys(pendingOverrides).length > 0) {
        // Start from current state
        const currentOverrides: Record<string, number> = {};
        for (const tool of tools) {
          if (tool.actions) {
            for (const a of tool.actions) {
              if (a.risk_override != null) {
                currentOverrides[`${tool.name}:${a.name}`] = a.risk_override;
              }
            }
          } else if (tool.risk_override != null) {
            currentOverrides[tool.name] = tool.risk_override;
          }
        }
        for (const [key, value] of Object.entries(pendingOverrides)) {
          if (value === null) delete currentOverrides[key];
          else currentOverrides[key] = value;
        }
        patch.tools_risk_overrides = currentOverrides;
      }

      const url = persist ? "/api/config/guardrails?persist=true" : "/api/config/guardrails";
      await apiPatch(url, patch);
      setPendingOverrides({});
      setPendingDeny(null);
      setPendingApproval({});
      mutate();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl">Tools</h1>
          {tools && tools.length > 0 && (
            <Badge variant="secondary">{tools.length}</Badge>
          )}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        View and configure the tools Squire has access to.
      </p>

      {!tools || tools.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
          <Wrench className="h-8 w-8" />
          <p className="text-sm">No tools registered</p>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Approval</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Override</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tools.map((tool) => {
                const isMulti = tool.actions && tool.actions.length > 0;
                const isExpanded = expanded.has(tool.name);
                return (
                  <>
                    <TableRow
                      key={tool.name}
                      className="hover:bg-muted/50 cursor-pointer"
                      onClick={() => isMulti && toggleExpand(tool.name)}
                    >
                      <TableCell className="font-medium">
                        <span className="flex items-center gap-1.5">
                          {isMulti && (
                            <ChevronRight
                              className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                            />
                          )}
                          {tool.name}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={GROUP_COLORS[tool.group] ?? ""}>
                          {tool.group}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {tool.risk_level != null ? (
                          <RiskBadge level={tool.risk_level} override={tool.risk_override} />
                        ) : (
                          <span className="text-xs text-muted-foreground">per-action</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Select
                          value={getEffectiveApproval(tool) ?? "default"}
                          onValueChange={(v) => handleApprovalChange(tool.name, v)}
                        >
                          <SelectTrigger className="h-7 w-[120px] text-xs" onClick={(e) => e.stopPropagation()}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="default">Risk-based</SelectItem>
                            <SelectItem value="always">Always</SelectItem>
                            <SelectItem value="never">Auto-allow</SelectItem>
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Switch
                          checked={getEffectiveStatus(tool)}
                          onCheckedChange={() => handleToggleStatus(tool)}
                          size="sm"
                        />
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {tool.risk_level != null && (
                          <Input
                            type="number"
                            min={1}
                            max={5}
                            className="w-16 h-7 text-xs"
                            placeholder="-"
                            value={
                              tool.name in pendingOverrides
                                ? pendingOverrides[tool.name] ?? ""
                                : tool.risk_override ?? ""
                            }
                            onChange={(e) => {
                              const v = e.target.value ? parseInt(e.target.value, 10) : null;
                              if (v !== null && (v < 1 || v > 5)) return;
                              handleOverride(tool.name, v);
                            }}
                          />
                        )}
                      </TableCell>
                    </TableRow>
                    {isMulti && isExpanded &&
                      tool.actions!.map((action) => (
                        <ActionRow
                          key={`${tool.name}:${action.name}`}
                          toolName={tool.name}
                          action={action}
                          onOverride={handleOverride}
                        />
                      ))}
                  </>
                );
              })}
            </TableBody>
          </Table>

          {hasPending && (
            <div className="flex items-center justify-between pt-2 border-t">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={persist}
                  onChange={(e) => setPersist(e.target.checked)}
                  className="rounded"
                />
                Save to disk
              </label>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5 mr-1" />
                )}
                Save Changes
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd web && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add web/src/app/tools/page.tsx
git commit -m "feat(web): add /tools page with catalog table and config controls"
```

---

### Task 8: Run full CI checks and update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run linter**

Run: `uv run ruff check src/squire/api/routers/tools.py src/squire/callbacks/risk_gate.py src/squire/config/guardrails.py`
Expected: No errors (fix any that appear)

- [ ] **Step 2: Run formatter check**

Run: `uv run ruff format --check src/squire/api/routers/tools.py src/squire/callbacks/risk_gate.py src/squire/config/guardrails.py`
Expected: All files formatted (fix any that aren't)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Update CHANGELOG.md**

Add under `## [Unreleased]` → `### Added`:

```markdown
- **Tools visibility & configuration page** — view all tools with metadata and configure per-tool policies
  - `GET /api/tools` endpoint returns the full tool catalog with name, description, group, parameters, risk levels, and effective guardrails
  - `tools_risk_overrides` field on `GuardrailsConfig` for per-tool (or per-action) risk level overrides
  - Risk gate applies overrides before evaluation — overridden risk levels flow through host/force escalation
  - `/tools` page with sortable table, collapsible multi-action rows, inline risk override inputs, approval policy dropdown, and enable/disable toggle
  - Config changes save through existing `PATCH /api/config/guardrails` with optional persist to `squire.toml`
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add tools visibility feature to CHANGELOG"
```
