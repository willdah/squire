"""TOML configuration file loader.

Loads squire.toml from standard locations and returns section dicts
that can be passed as overrides when constructing config classes.
Env vars still take precedence (handled by pydantic-settings).

Search order:
  1. ./squire.toml (project directory)
  2. ~/.config/squire/squire.toml (user config)
  3. /etc/squire/squire.toml (system-wide)
"""

import os
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import tomlkit
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


def get_section(name: str, preserve: set[str] | None = None) -> dict:
    """Get a TOML section by name, returning {} if not found.

    Nested sub-tables are flattened with underscore-joined keys.
    For example, ``[guardrails.watch]`` with ``tolerance = "read-only"``
    becomes ``{"watch_tolerance": "read-only"}`` in the returned dict.

    Args:
        name: TOML section name (e.g. ``"guardrails"``).
        preserve: Sub-table keys to keep as nested dicts instead of flattening.
            Use this for fields that map to nested Pydantic models (e.g. ``{"email"}``).
    """
    data = _load_toml()
    section = data.get(name, {})
    if not isinstance(section, dict):
        return {}
    section = dict(section)  # shallow copy to avoid mutating cache
    preserve = preserve or set()
    for sub_key in list(section):
        if isinstance(section[sub_key], dict) and sub_key not in preserve:
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


def invalidate_cache() -> None:
    """Clear the cached TOML data so the next read reloads from disk."""
    global _cached
    _cached = None


def get_toml_path() -> Path | None:
    """Return the path of the first existing squire.toml, or None."""
    for path in _SEARCH_PATHS:
        if path.is_file():
            return path.resolve()
    return None


def get_env_overrides(prefix: str, field_names: Iterable[str]) -> list[str]:
    """Return field names whose values are currently set via environment variables."""
    overridden = []
    for name in field_names:
        env_key = f"{prefix}{name.upper()}"
        if env_key in os.environ:
            overridden.append(name)
    return overridden


def write_toml_section(section: str | None, data: dict) -> Path:
    """Write config values to the TOML file, preserving comments and formatting.

    Args:
        section: TOML section name (e.g. ``"llm"``), or ``None`` for top-level keys.
        data: Field names and values to write.

    Returns:
        Path to the written file.
    """
    path = get_toml_path()
    if path is None:
        # Create at the first search path location (project-local by default)
        path = _SEARCH_PATHS[0].resolve()

    if path.is_file():
        with open(path) as f:
            doc = tomlkit.load(f)
    else:
        doc = tomlkit.document()
        path.parent.mkdir(parents=True, exist_ok=True)

    if section is None:
        for k, v in data.items():
            doc[k] = v
    else:
        if section not in doc:
            doc[section] = tomlkit.table()
        for k, v in data.items():
            doc[section][k] = v

    with open(path, "w") as f:
        tomlkit.dump(doc, f)

    invalidate_cache()
    return path


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
