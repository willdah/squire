# CI/CD Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve CI/CD reliability by fixing the broken Dockerfile, splitting CI into parallel jobs with caching, adding frontend validation, Docker build verification, and Dependabot.

**Architecture:** Restructure the single `ci.yml` workflow into parallel jobs (lint, test, frontend, docker). Add `.dockerignore` and fix the Dockerfile's missing `packages/` copy. Add Dependabot for automated dependency updates across all three ecosystems.

**Tech Stack:** GitHub Actions, Docker, uv, Node.js/npm, Dependabot

---

### Task 1: Fix the Dockerfile

The Dockerfile cannot build because it never copies the `packages/` directory, which contains the `agent-risk-engine` local dependency required by `pyproject.toml`.

**Files:**
- Modify: `docker/Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Add `.dockerignore`**

Create `.dockerignore` at the repo root to prevent bloating the Docker build context:

```
.git
.github
.venv
.mypy_cache
.pytest_cache
.ruff_cache
__pycache__
*.egg-info
dist
build
docs
tests
web/node_modules
web/.next
.claude
.env
*.md
!README.md
```

- [ ] **Step 2: Fix the Dockerfile**

Replace the full contents of `docker/Dockerfile` with:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency metadata first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY README.md ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application source
COPY src/ src/

# Default environment
ENV SQUIRE_RISK_PROFILE=cautious
ENV SQUIRE_DB_PATH=/data/squire.db

VOLUME ["/data"]

ENTRYPOINT ["uv", "run", "squire"]
CMD ["chat"]
```

Key changes:
- Adds `COPY packages/ packages/` so the local `agent-risk-engine` dependency resolves
- Uses explicit `uv.lock` (not glob `uv.lock*`) — the lockfile must exist
- Copies `src/` after `uv sync` so dependency layers are cached when only app code changes

- [ ] **Step 3: Verify the Docker image builds**

```bash
docker build -f docker/Dockerfile -t squire:test .
```

Expected: Build completes successfully. The `uv sync` step should resolve `agent-risk-engine` from the local `packages/` directory.

- [ ] **Step 4: Commit**

```bash
git add .dockerignore docker/Dockerfile
git commit -m "fix: Dockerfile — add missing packages/ copy and .dockerignore"
```

---

### Task 2: Restructure CI into parallel jobs with caching

Split the single `lint-and-test` job into three parallel jobs: `lint` (single Python, no matrix), `test` (Python matrix), and `frontend`. All jobs enable dependency caching.

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Rewrite ci.yml**

Replace the full contents of `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.13

      - name: Install dependencies
        run: uv sync --dev

      - name: Lint
        run: uv run ruff check src/ tests/

      - name: Format check
        run: uv run ruff format --check src/ tests/

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --dev

      - name: Test
        run: uv run pytest

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Build
        run: npm run build

  docker:
    runs-on: ubuntu-latest
    needs: [lint, test, frontend]
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -f docker/Dockerfile -t squire:ci .
```

Key design decisions:
- `lint` runs on a single Python version (3.13) — ruff output is identical across versions
- `test` keeps the 3.12/3.13 matrix for runtime compatibility
- `frontend` uses Node 22 LTS and `npm ci` for reproducible installs
- `docker` runs after all other jobs pass — verifies the image builds but does not push
- All jobs use dependency caching (`enable-cache` for uv, `cache: npm` for Node)

- [ ] **Step 2: Verify the workflow is valid YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: split into parallel lint/test/frontend/docker jobs with caching"
```

---

### Task 3: Add Dependabot configuration

Configure Dependabot to watch Python, npm, and GitHub Actions dependencies for security patches and version updates.

**Files:**
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Create dependabot.yml**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  # Python dependencies (pyproject.toml)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "python"

  # Frontend dependencies (web/package.json)
  - package-ecosystem: "npm"
    directory: "/web"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "javascript"

  # GitHub Actions versions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "ci"
```

- [ ] **Step 2: Commit**

```bash
git add .github/dependabot.yml
git commit -m "ci: add Dependabot for Python, npm, and GitHub Actions"
```

---

### Task 4: Update Makefile for local CI parity

Update `make ci` to include frontend checks so developers can run the same validations locally that CI runs.

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Update the `ci` target**

In `Makefile`, change line 37:

```makefile
ci: lint format-check test ## Run the full CI pipeline locally
```

to:

```makefile
ci: lint format-check test web-lint web-build ## Run the full CI pipeline locally
```

- [ ] **Step 2: Verify make ci runs**

```bash
make ci
```

Expected: lint, format-check, test, web-lint, and web-build all run in sequence. All should pass.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "chore: add frontend checks to make ci target"
```

---

### Task 5: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add CI/CD entry under [Unreleased]**

Add the following under the `## [Unreleased]` section, after the existing entries. If there's no `### Changed` subsection yet, add one:

```markdown
### Changed

- **CI/CD improvements** — split CI into parallel jobs (lint, test, frontend, docker) with dependency caching. Fixed broken Dockerfile (missing `packages/` copy). Added `.dockerignore`. Added Dependabot for Python, npm, and GitHub Actions. `make ci` now includes frontend lint and build checks.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CI/CD improvements to CHANGELOG"
```
