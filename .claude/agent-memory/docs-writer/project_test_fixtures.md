---
name: Test fixture patterns
description: How MockBackend and MockRegistry work in tests — for writing accurate testing docs
type: project
---

`tests/conftest.py` provides three fixtures:

- `mock_backend` — `MockBackend` instance; register canned responses with `set_response(cmd_prefix, CommandResult)` matching by first token or full command string prefix
- `mock_registry` — `MockRegistry` wrapping `mock_backend`; installs itself as the global registry via `set_registry()` before yielding and tears down with `set_registry(None)` after
- `db` — temporary `DatabaseService` backed by `tmp_path / "test.db"`; async fixture

Always use `mock_registry` (not `mock_backend` alone) in tests that call `get_registry()`, otherwise the global registry is not set.

`asyncio_mode = "auto"` means no `@pytest.mark.asyncio` decorator needed on async test functions.
