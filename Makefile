.DEFAULT_GOAL := help

# Absolute path to the repo root (Makefile location). Keeps web build/serve aligned
# even when Make is invoked with -C or from an unexpected working directory.
REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

.PHONY: install
install: ## Install Python and frontend dependencies
	cd $(REPO_ROOT) && uv sync --dev
	cd $(REPO_ROOT)/web && npm install

.PHONY: lint
lint: ## Run ruff linter
	cd $(REPO_ROOT) && uv run ruff check src/ tests/

.PHONY: format
format: ## Auto-format Python code with ruff
	cd $(REPO_ROOT) && uv run ruff format src/ tests/

.PHONY: format-check
format-check: ## Check Python formatting (no changes)
	cd $(REPO_ROOT) && uv run ruff format --check src/ tests/

.PHONY: typecheck
typecheck: ## Run mypy type checking
	cd $(REPO_ROOT) && uv run mypy src/

.PHONY: test
test: ## Run pytest suite
	cd $(REPO_ROOT) && uv run pytest

.PHONY: test-v
test-v: ## Run pytest with verbose output
	cd $(REPO_ROOT) && uv run pytest -v

.PHONY: ci
ci: lint format-check test web-lint web-build ## Run the full CI pipeline locally

# ---------------------------------------------------------------------------
# Frontend (web/)
# ---------------------------------------------------------------------------

.PHONY: web-install
web-install: ## Install frontend dependencies
	cd $(REPO_ROOT)/web && npm install

.PHONY: web-dev
web-dev: ## Start Next.js dev server
	cd $(REPO_ROOT)/web && npm run dev

.PHONY: web-build
web-build: ## Build Next.js static export into web/out (required for bundled UI)
	cd $(REPO_ROOT)/web && npm run build

.PHONY: web-lint
web-lint: ## Lint frontend code
	cd $(REPO_ROOT)/web && npm run lint

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

.PHONY: web
web: web-build ## Build Next.js export then start FastAPI + static UI
	cd $(REPO_ROOT) && SQUIRE_WEB_STATIC_DIR=$(REPO_ROOT)/web/out uv run squire web --reload

.PHONY: watch
watch: ## Start autonomous watch mode
	cd $(REPO_ROOT) && uv run squire watch

.PHONY: webhook-receiver
webhook-receiver: ## Dev-only HTTP server to capture Squire notification webhooks
	cd $(REPO_ROOT) && uv run python scripts/webhook_receiver.py

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

.PHONY: docker-build
docker-build: ## Build Docker image
	cd $(REPO_ROOT) && docker build -f docker/Dockerfile -t squire .

.PHONY: docker-run
docker-run: ## Run Docker container (web UI on port 8420)
	docker run --rm -d -p 8420:8420 -v squire-data:/data --name squire squire

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

.PHONY: clean
clean: ## Remove Python caches and build artifacts
	cd $(REPO_ROOT) && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	cd $(REPO_ROOT) && find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	cd $(REPO_ROOT) && find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	cd $(REPO_ROOT) && find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(REPO_ROOT)/dist/ $(REPO_ROOT)/build/ $(REPO_ROOT)/*.egg-info $(REPO_ROOT)/src/*.egg-info

.PHONY: clean-web
clean-web: ## Remove frontend build output, cache, and node_modules
	rm -rf $(REPO_ROOT)/web/.next $(REPO_ROOT)/web/out $(REPO_ROOT)/web/node_modules

.PHONY: clean-all
clean-all: clean clean-web ## Remove all generated files

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
