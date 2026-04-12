---
name: Doc surface map (watch / API / UI)
description: Where user-facing docs describe watch mode, Activity API, and web routes; updated 2026-04-12 for Explorer parity.
type: reference
---

- **usage.md** — Web UI page table, watch getting-started narrative; primary entry for operators.
- **architecture.md** — Database tables, high-level watch + Explorer mention, `web/src/app` route list.
- **design/watch-web-integration.md** — Detailed watch IPC, REST/WS, retention, Explorer; keep in sync with `watch.py`, `events.py`, `database/service.py`.
- **configuration.md** — `[watch]`, `[guardrails.watch]`, notifications; not duplicated for per-endpoint REST.
- **README.md** — Short UI feature list only.

CHANGELOG convention: substantive doc parity edits get a **Documentation** bullet under Unreleased → Changed.
