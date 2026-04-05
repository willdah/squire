---
name: CI/CD baseline state (2026-04-04)
description: Comprehensive snapshot of CI/CD configuration — single GHA workflow, Dockerfile gaps, no frontend CI, no caching, no security scanning
type: project
---

As of 2026-04-04, Squire has a minimal CI/CD setup.

**What exists:**
- Single GHA workflow `.github/workflows/ci.yml`: ruff check, ruff format --check, pytest on Python 3.12+3.13 matrix. Uses astral-sh/setup-uv@v4. No caching, no frontend checks.
- Dockerfile at `docker/Dockerfile`: single-stage python:3.12-slim, copies pyproject.toml + src/ only. Missing `packages/agent-risk-engine/` (build will fail), missing `web/` static export, missing uv.lock COPY.
- Makefile has `make ci` = lint + format-check + test (Python only). Also has `web-build`, `web-lint`, `typecheck` (mypy), `docker-build` targets.
- 232 pytest tests (collected in ~0.67s). ~2585 lines of test code across 27 test files.
- `packages/agent-risk-engine` has its own test suite (8 test files) with test extras but is not tested in GHA.
- ESLint configured in `web/eslint.config.mjs` (next core-web-vitals + typescript). `npm run lint` available.
- No pre-commit hooks, no Dependabot, no security scanning, no Docker image CI builds.
- Issue templates exist (.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md).
- uv.lock and web/package-lock.json both committed.

**Key gaps identified:**
1. Dockerfile is broken — missing `packages/agent-risk-engine/` COPY
2. No frontend CI (build/lint/typecheck)
3. No dependency caching in GHA
4. No security scanning (deps or containers)
5. No Docker build verification
6. No release/tagging automation
7. mypy in Makefile but not in CI
8. `packages/agent-risk-engine` tests not run in CI

**Why:** Baseline for planning CI/CD improvements.
**How to apply:** Reference when prioritizing workflow additions and measuring improvement.
