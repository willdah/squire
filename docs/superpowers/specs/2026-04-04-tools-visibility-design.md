# Tools Visibility & Configuration — Design Spec

**Date:** 2026-04-04
**Status:** Draft

## Overview

Add a `/tools` page to the Squire web UI that lets users view all available tools with their metadata (description, parameters, risk levels, agent group) and configure per-tool policies: enable/disable, risk level overrides, and approval policy overrides.

## Goals

- Users can see every tool Squire has access to, what it does, and what risk it carries
- Users can disable tools they don't want Squire to use
- Users can override per-tool risk levels
- Users can set per-tool approval policies (always require, auto-allow, or risk-based default)
- Configuration can be applied at runtime and optionally persisted to `squire.toml`

## Non-Goals

- Per-host tool configuration (global only for now)
- Usage analytics / invocation history on this page
- Configuring default parameter values for tools

## Data Model

### Leveraging Existing GuardrailsConfig

The existing `GuardrailsConfig` already provides:

- `tools_allow: list[str]` — tools that bypass risk check and auto-run
- `tools_require_approval: list[str]` — tools that always require approval
- `tools_deny: list[str]` — tools that are hard-blocked

These map directly to the required configuration actions:

| User Action | Guardrails Field |
|---|---|
| Disable a tool | Add to `tools_deny` |
| Set approval to "always" | Add to `tools_require_approval` |
| Set approval to "auto-allow" | Add to `tools_allow` |
| Reset to risk-based default | Remove from all three lists |

### New Field: `tools_risk_overrides`

One new field is needed on `GuardrailsConfig`:

```python
tools_risk_overrides: dict[str, int] = Field(
    default_factory=dict,
    description="Per-tool risk level overrides. Keys are tool names or tool:action compound names. Values are 1-5.",
)
```

This allows overriding the base risk level of any tool or action (e.g., `{"docker_container:remove": 5}`).

### Risk Gate Integration

The risk gate callback already reads `tools_deny`, `tools_allow`, and `tools_require_approval`. It needs to additionally read `tools_risk_overrides` to substitute base risk levels before evaluation. When a tool is in `tools_deny`, the agent is told the tool is disabled (not hidden — it can explain this to the user).

### List Conflict Resolution

A tool should only appear in one of `tools_deny`, `tools_require_approval`, or `tools_allow`. The frontend enforces this by removing the tool from the other lists when adding it to one. If a conflict exists in the raw config, precedence is: `tools_deny` > `tools_require_approval` > `tools_allow`.

### Config Precedence

Unchanged from existing system: env vars > `squire.toml` > defaults. The web UI writes through `PATCH /api/config/guardrails` with optional `?persist=true` to write to `squire.toml`.

## API Design

### `GET /api/tools` — Tool Catalog

New read-only endpoint that introspects the tool registry and merges effective configuration.

**Response:** `ToolInfo[]`

```json
[
  {
    "name": "docker_container",
    "description": "Manage Docker container lifecycle.",
    "group": "container",
    "parameters": [
      {"name": "action", "type": "string", "required": true},
      {"name": "container", "type": "string", "required": true},
      {"name": "host", "type": "string", "default": "local"}
    ],
    "actions": [
      {"name": "inspect", "risk_level": 1, "risk_override": null},
      {"name": "start",   "risk_level": 3, "risk_override": null},
      {"name": "stop",    "risk_level": 3, "risk_override": null},
      {"name": "restart", "risk_level": 3, "risk_override": null},
      {"name": "remove",  "risk_level": 4, "risk_override": 5}
    ],
    "status": "enabled",
    "approval_policy": null
  },
  {
    "name": "system_info",
    "description": "Get system information for a host.",
    "group": "monitor",
    "parameters": [
      {"name": "host", "type": "string", "default": "local"}
    ],
    "actions": null,
    "risk_level": 1,
    "risk_override": null,
    "status": "enabled",
    "approval_policy": "always"
  }
]
```

**Field definitions:**

- `name`: Tool function name
- `description`: First line of docstring
- `group`: Agent group from `groups.py` (monitor, container, admin)
- `parameters`: Extracted from function signature — name, type, required flag, default value
- `actions`: For multi-action tools only — list of action objects with per-action risk info. `null` for single-action tools.
- `risk_level`: Base risk level (single-action tools only; multi-action tools have this on each action)
- `risk_override`: Value from `tools_risk_overrides` if set, else `null`
- `status`: `"enabled"` or `"disabled"` (derived from `tools_deny`)
- `approval_policy`: `"always"` (in `tools_require_approval`), `"never"` (in `tools_allow`), or `null` (risk-based default)

### Tool Configuration — No New Write Endpoint

All tool config changes go through the existing `PATCH /api/config/guardrails` endpoint. The frontend computes the updated guardrails lists/dict and sends the patch. Examples:

- Disable `run_command`: `PATCH /api/config/guardrails` with `{"tools_deny": ["run_command", ...existing]}`
- Override risk for `docker_container:remove`: `PATCH /api/config/guardrails` with `{"tools_risk_overrides": {"docker_container:remove": 5}}`

## Frontend Design

### Navigation

New `/tools` page in the sidebar "System" nav group (alongside Hosts, Notifications, Config). Icon: `Wrench` from lucide-react.

### Page Layout

Follows the skills page pattern:

- **Header:** "Tools" title + badge with total tool count
- **Description:** "View and configure the tools Squire has access to."
- **Table** with columns:
  - **Name** — tool name, with chevron for multi-action tools
  - **Group** — badge showing agent group (monitor, container, admin)
  - **Risk** — colored badge (1=green, 2=blue, 3=yellow, 4=orange, 5=red); shows override value if set
  - **Approval** — policy badge: "Risk-based" (default), "Always", or "Auto-allow"
  - **Status** — enabled/disabled toggle switch
  - **Actions** — settings icon to open config controls

### Collapsible Multi-Action Rows

Multi-action tools (e.g., `docker_container` with inspect/start/stop/restart/remove) display a chevron. Expanding reveals sub-rows for each action with their individual risk levels and per-action risk override controls.

### Configuration Controls

Accessed via settings icon on each row (slide-out panel or inline expansion):

- **Risk override:** Number input (1-5) with "reset to default" option. For multi-action tools, overrides are per-action.
- **Approval policy:** Dropdown — "Risk-based (default)", "Always require approval", "Auto-allow"
- **Enable/Disable:** Toggle switch directly in the table row

### Save Behavior

Changes call `PATCH /api/config/guardrails` immediately for runtime effect. A "Persist to squire.toml" toggle or button lets users optionally persist via `?persist=true` — same pattern the config page uses.

## Schema Additions

### Python (Pydantic)

```python
# In schemas.py
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
    risk_level: int | None = None       # single-action tools only
    risk_override: int | None = None    # single-action tools only
    status: str                          # "enabled" | "disabled"
    approval_policy: str | None = None  # "always" | "never" | null

# New field on GuardrailsConfig
tools_risk_overrides: dict[str, int] = Field(
    default_factory=dict,
    description="Per-tool risk level overrides (tool name or tool:action -> 1-5)",
)

# Addition to GuardrailsConfigUpdate
tools_risk_overrides: dict[str, int] | None = None
```

### TypeScript

```typescript
// In types.ts
interface ToolParameter {
  name: string;
  type: string;
  required: boolean;
  default?: string;
}

interface ToolAction {
  name: string;
  risk_level: number;
  risk_override: number | null;
}

interface ToolInfo {
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

## Implementation Summary

1. **Backend:** Add `tools_risk_overrides` field to `GuardrailsConfig` and `GuardrailsConfigUpdate`. Create `GET /api/tools` endpoint that introspects the tool registry. Update risk gate to read `tools_risk_overrides`.
2. **Frontend:** Add `/tools` page with catalog table, collapsible multi-action rows, inline config controls. Add sidebar nav entry. Wire config changes through existing guardrails PATCH endpoint.
3. **Tests:** Tool catalog endpoint tests, risk gate override tests, guardrails config round-trip tests.
