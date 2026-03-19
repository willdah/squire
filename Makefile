.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

.PHONY: install
install: ## Install Python and frontend dependencies
	uv sync --dev
	cd web && npm install

.PHONY: lint
lint: ## Run ruff linter
	uv run ruff check src/ tests/

.PHONY: format
format: ## Auto-format Python code with ruff
	uv run ruff format src/ tests/

.PHONY: format-check
format-check: ## Check Python formatting (no changes)
	uv run ruff format --check src/ tests/

.PHONY: typecheck
typecheck: ## Run mypy type checking
	uv run mypy src/

.PHONY: test
test: ## Run pytest suite
	uv run pytest

.PHONY: test-v
test-v: ## Run pytest with verbose output
	uv run pytest -v

.PHONY: ci
ci: lint format-check test ## Run the full CI pipeline locally

# ---------------------------------------------------------------------------
# Frontend (web/)
# ---------------------------------------------------------------------------

.PHONY: web-install
web-install: ## Install frontend dependencies
	cd web && npm install

.PHONY: web-dev
web-dev: ## Start Next.js dev server
	cd web && npm run dev

.PHONY: web-build
web-build: ## Build Next.js for production
	cd web && npm run build

.PHONY: web-lint
web-lint: ## Lint frontend code
	cd web && npm run lint

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

.PHONY: chat
chat: ## Start the TUI chat interface
	uv run squire chat

.PHONY: web
web: ## Start the web interface (FastAPI + static frontend)
	uv run squire web --reload

.PHONY: watch
watch: ## Start autonomous watch mode
	uv run squire watch

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

.PHONY: docker-build
docker-build: ## Build Docker image
	docker build -f docker/Dockerfile -t squire .

.PHONY: docker-run
docker-run: ## Run Docker container
	docker run --rm -it -v squire-data:/data squire

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

.PHONY: clean
clean: ## Remove Python caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info src/*.egg-info

.PHONY: clean-web
clean-web: ## Remove frontend build artifacts and node_modules
	rm -rf web/.next web/node_modules

.PHONY: clean-all
clean-all: clean clean-web ## Remove all generated files

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
