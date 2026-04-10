---
name: Tool registration pattern
description: How tools are authored and registered in Squire — important for accurate docs and contributor guidance
type: project
---

Tools in `src/squire/tools/` are plain async functions. The `safe_tool` wrapper is NOT applied inside tool modules — it is applied at registration time in `src/squire/tools/__init__.py` via `ALL_TOOLS = [..., safe_tool(my_tool), ...]`.

Each tool module defines `RISK_LEVEL: int` (single-action) or `RISK_LEVELS: dict[str, int]` (multi-action, keys are `"tool_name:action"`). These are imported into `TOOL_RISK_LEVELS` in `__init__.py`, which the risk gate callback reads.

Tools are not registered per-agent — they are all gathered in `ALL_TOOLS` and distributed to agents from there.

**Why:** Accurate contributor docs require knowing this; the previous CONTRIBUTING.md implied `@safe_tool` was a decorator to apply in the module, which is wrong.

**How to apply:** When documenting tool authoring, always show `safe_tool` applied in `__init__.py`, not on the function definition.
