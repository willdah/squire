"""TOML configuration file loader.

Loads squire.toml from standard locations and returns section dicts
that can be passed as overrides when constructing config classes.
Env vars still take precedence (handled by pydantic-settings).

Search order:
  1. ./squire.toml (project directory)
  2. ~/.config/squire/squire.toml (user config)
  3. /etc/squire/squire.toml (system-wide)
"""

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

_SEARCH_PATHS = [
    Path("squire.toml"),
    Path.home() / ".config" / "squire" / "squire.toml",
    Path("/etc/squire/squire.toml"),
]

_cached: dict | None = None


def _load_toml() -> dict:
    """Load the first squire.toml found in search paths."""
    global _cached
    if _cached is not None:
        return _cached

    for path in _SEARCH_PATHS:
        if path.is_file():
            with open(path, "rb") as f:
                _cached = tomllib.load(f)
                return _cached

    _cached = {}
    return _cached


def get_section(name: str) -> dict:
    """Get a TOML section by name, returning {} if not found.

    Nested sub-tables are flattened with underscore-joined keys.
    For example, ``[guardrails.watch]`` with ``tolerance = "read-only"``
    becomes ``{"watch_tolerance": "read-only"}`` in the returned dict.
    """
    data = _load_toml()
    section = data.get(name, {})
    if not isinstance(section, dict):
        return {}
    section = dict(section)  # shallow copy to avoid mutating cache
    for sub_key in list(section):
        if isinstance(section[sub_key], dict):
            nested = section.pop(sub_key)
            for k, v in nested.items():
                section[f"{sub_key}_{k}"] = v
    return section


def get_list_section(name: str) -> list[dict]:
    """Get a TOML array-of-tables section by name, returning [] if not found."""
    data = _load_toml()
    section = data.get(name, [])
    return section if isinstance(section, list) else []


def get_top_level() -> dict:
    """Get top-level keys (everything not in a sub-table)."""
    data = _load_toml()
    return {k: v for k, v in data.items() if not isinstance(v, (dict, list))}


class TomlSectionSource(PydanticBaseSettingsSource):
    """A pydantic-settings source that reads from a TOML section.

    Inserted after env_settings so env vars take precedence over TOML.
    """

    def __init__(self, settings_cls: type[BaseSettings], section_loader: Callable[[], dict]) -> None:
        super().__init__(settings_cls)
        self._section_loader = section_loader

    def get_field_value(self, field, field_name: str) -> tuple[Any, str, bool]:
        data = self._section_loader()
        val = data.get(field_name)
        return val, field_name, val is not None

    def __call__(self) -> dict[str, Any]:
        data = self._section_loader()
        # Only return keys that exist in the model
        field_names = set(self.settings_cls.model_fields.keys())
        return {k: v for k, v in data.items() if k in field_names}
