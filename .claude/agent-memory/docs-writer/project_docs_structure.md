---
name: Docs structure and coverage map
description: Which docs files exist, what they cover, and their freshness as of 2026-04-05
type: project
---

Docs live in `/Users/will/Projects/squire/docs/`. The project follows a "front door" pattern — README is a slim landing page, detailed content lives in docs/.

**Current docs files:**
- `docs/architecture.md` — NEW (2026-04-05). System overview, agent modes, request/risk/watch flows, tech stack, DB schema, backend registry. Contains Mermaid diagrams.
- `docs/usage.md` — comprehensive usage guide: interfaces (web/TUI/CLI), configuration, remote hosts, multi-agent mode, watch mode, alert rules, skills, notifications, Docker. Created 2026-04-05.
- `docs/cli.md` — full CLI reference: every command and flag documented. Accurate as of 2026-04-05.
- `docs/configuration.md` — full configuration reference: all sections, env vars, guardrails, watch mode, notifications. Accurate as of 2026-04-05.
- `docs/todos.md` — internal todos, not user-facing.
- `docs/design/` — design specs and implementation plans (internal).
- `docs/superpowers/` — skill-related internal docs.
- `docs/assets/` — images/assets.

**Why:** README is being slimmed to a landing page; usage.md is the "deep dive" it links to. architecture.md targets contributors and power users who want to understand internals.

**How to apply:** When writing new user-facing docs, place them in `docs/`. Cross-link from architecture.md to configuration.md and cli.md. The docs cross-reference pattern is: usage.md → cli.md for flag details, usage.md → configuration.md for config details, architecture.md → configuration.md for config references.
