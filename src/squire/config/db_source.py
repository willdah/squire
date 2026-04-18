"""Pydantic settings source that reads UI-driven overrides from the SQLite DB.

Mirrors ``TomlSectionSource`` but pulls from the ``config_overrides`` table.
Sync-only because pydantic-settings sources run during ``BaseSettings.__init__``;
uses ``sqlite3`` rather than the async ``aiosqlite`` wrapper.

Precedence for every mutable config: env > DB > TOML > default. This module
implements the DB layer; the TOML layer lives in ``loader.py``.

``DatabaseConfig`` deliberately does NOT consume this source — resolving the DB
path would create a chicken-and-egg problem. See ``_resolve_db_path`` below,
which re-derives the path from env, TOML, and the hardcoded default without
instantiating ``DatabaseConfig``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class DatabaseOverrideSource(PydanticBaseSettingsSource):
    """Load UI-driven field overrides for a given config section."""

    def __init__(self, settings_cls: type[BaseSettings], section: str) -> None:
        super().__init__(settings_cls)
        self._section = section

    def _resolve_db_path(self) -> Path:
        env = os.environ.get("SQUIRE_DB_PATH")
        if env:
            return Path(env)
        # Avoid importing at module scope to keep the import graph shallow.
        from .loader import get_section

        toml_path = get_section("db").get("path")
        if toml_path:
            return Path(toml_path)
        return Path.home() / ".local" / "share" / "squire" / "squire.db"

    def _load(self) -> dict[str, Any]:
        try:
            path = self._resolve_db_path()
            if not path.exists():
                return {}
            with sqlite3.connect(path) as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                rows = conn.execute(
                    "SELECT field, value_json FROM config_overrides WHERE section = ?",
                    (self._section,),
                ).fetchall()
        except (sqlite3.OperationalError, FileNotFoundError):
            # Pre-schema / first boot — behave as if no overrides exist.
            return {}
        return {field: json.loads(value_json) for field, value_json in rows}

    def get_field_value(self, field, field_name: str) -> tuple[Any, str, bool]:
        data = self._load()
        val = data.get(field_name)
        return val, field_name, val is not None

    def __call__(self) -> dict[str, Any]:
        data = self._load()
        field_names = set(self.settings_cls.model_fields.keys())
        return {k: v for k, v in data.items() if k in field_names}
