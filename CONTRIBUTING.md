# Contributing to Squire

Thanks for your interest in contributing! Here's how to get started.

## Development setup

1. **Clone the repo**:

   ```bash
   git clone https://github.com/<owner>/squire.git
   cd squire
   ```

2. **Install dependencies** with [uv](https://docs.astral.sh/uv/):

   ```bash
   uv sync --dev
   ```

3. **Run the linter and tests:**

   ```bash
   uv run ruff check src/ tests/
   uv run pytest
   ```

## Project layout

```
src/squire/          Main application
tests/               Pytest test suite
```

## Making changes

1. Create a branch from `main`.
2. Make your changes, keeping commits focused.
3. Ensure `ruff check` and `pytest` pass.
4. Open a pull request against `main`.

## Code style

- Python 3.12+, formatted with **ruff**.
- Line length: 120 characters.
- All tools are async functions returning `str`.
- Prefer returning error strings over raising exceptions in tool functions.

## Reporting issues

Open a GitHub issue with:
- Steps to reproduce
- Expected vs. actual behavior
- Python version and OS
