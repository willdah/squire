---
name: bump-version
description: Use when bumping the Squire package version, cutting a release, or syncing version strings across pyproject, lockfile, __init__, and CHANGELOG.
---

# Bump version

## Overview

Squire’s published version must stay consistent in three places: `pyproject.toml`, `uv.lock` (workspace package entry for `squire`), and `src/squire/__init__.py`. `uv version` updates only `pyproject.toml`; the rest of the checklist is manual or `uv lock`. Always run CI-equivalent checks before claiming the bump is done.

## When to Use

- User asks to bump the version, tag a release, or prepare a release PR
- User invokes `/bump-version` or similar
- After merging features you are shipping in a single versioned release

## Semver

Choose the segment intentionally:

| Bump | When |
|------|------|
| **patch** | Bug fixes, small corrections, no API or behavior contract changes for integrators |
| **minor** | Additive changes, new features, backward-compatible behavior |
| **major** | Breaking changes to behavior, config, or public surfaces you treat as stable |

The maintainer picks `patch`, `minor`, or `major` (or an explicit version string) before running commands.

## Ordered checklist

Follow this order so files stay aligned.

### 1. CHANGELOG

1. Open [CHANGELOG.md](CHANGELOG.md).
2. Ensure everything shipping in this release is documented under `## [Unreleased]` (or add it there first).
3. Add a new section **immediately below** `[Unreleased]`:

   `## [X.Y.Z] — YYYY-MM-DD`

   Move the release notes from Unreleased into that section (keep the same subsections: Added, Changed, Fixed, etc., as appropriate).
4. Leave `## [Unreleased]` in place with an empty body (or a placeholder line you remove once the next work lands), matching project convention.

### 2. Bump `pyproject.toml` with uv

From the repository root:

```bash
uv version --bump patch   # or: minor | major
```

To set an exact version instead:

```bash
uv version 1.2.3
```

This updates `[project] version` in [pyproject.toml](pyproject.toml) only.

### 3. Refresh the lockfile

```bash
uv lock
```

This updates the editable `squire` package `version` in [uv.lock](uv.lock) so it matches `pyproject.toml`.

### 4. Sync `__version__` (required)

Set `__version__` in [src/squire/__init__.py](src/squire/__init__.py) to the **exact same string** as `[project] version` in `pyproject.toml`. The CLI (`squire --version`) reads this module attribute; forgetting this step is a common release bug.

### 5. Frontend `package.json` (optional)

[web/package.json](web/package.json) uses its own semver (currently not aligned with the Python package). **Do not** bump it unless project policy says the web app version should track the Python release.

## Verification

Run the same checks as CI before asserting the bump is complete:

```bash
make ci
```

Equivalent: `ruff check`, `ruff format --check`, and `pytest` (see [CLAUDE.md](CLAUDE.md)).

## After the bump

Commit the changes. Open a PR using the create-pr skill if you use structured PRs. Tag or publish a GitHub Release according to your release process (out of scope for this checklist).

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Only running `uv version` | Also run `uv lock` and edit `src/squire/__init__.py` |
| Editing `pyproject.toml` by hand without `uv lock` | Run `uv lock` so `uv.lock` matches |
| New CHANGELOG section without a date | Use `## [X.Y.Z] — YYYY-MM-DD` |
| Bumping `web/package.json` by habit | Skip unless policy requires it |
| Claiming done without `make ci` | Run `make ci` and report actual results |
