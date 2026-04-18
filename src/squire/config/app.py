from enum import StrEnum
from importlib.metadata import version as _pkg_version
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .db_source import DatabaseOverrideSource
from .loader import TomlSectionSource, get_top_level


class RiskTolerance(StrEnum):
    """Named risk-tolerance aliases accepted in config and env vars."""

    READ_ONLY = "read-only"
    CAUTIOUS = "cautious"
    STANDARD = "standard"
    FULL_TRUST = "full-trust"


_INT_TO_ALIAS: dict[int, str] = {1: "read-only", 2: "cautious", 3: "standard", 5: "full-trust"}


def _coerce_risk_tolerance(value: Any) -> str | None:
    """Accept int (1-3, 5) or string alias; normalise to a RiskTolerance value."""
    if value is None:
        return None
    if isinstance(value, int):
        if value in _INT_TO_ALIAS:
            return _INT_TO_ALIAS[value]
        raise ValueError(f"No alias for numeric tolerance {value}; valid: {list(_INT_TO_ALIAS.keys())}")
    if isinstance(value, str) and value.isdigit():
        return _coerce_risk_tolerance(int(value))
    return value


class AppConfig(BaseSettings):
    """Top-level application configuration.

    Loaded from squire.toml top-level keys and/or SQUIRE_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="SQUIRE_", case_sensitive=False, extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            DatabaseOverrideSource(settings_cls, "_top_"),
            TomlSectionSource(settings_cls, get_top_level),
            file_secret_settings,
        )

    version: str = Field(
        default_factory=lambda: _pkg_version("squire"),
        description="Package version (read-only, from importlib.metadata)",
    )
    app_name: str = Field(
        default="Squire",
        description="Application name passed to the ADK runner",
    )
    user_id: str = Field(
        default="squire-user",
        description="User ID for ADK session management",
    )
    history_limit: int = Field(
        default=50,
        ge=1,
        description="Maximum number of messages kept in conversation context",
    )
    max_tool_rounds: int = Field(
        default=10,
        ge=1,
        description="Maximum tool-call rounds per user message",
    )
    multi_agent: bool = Field(
        default=False,
        description="Enable sub-agent decomposition (Monitor, Container, Admin, Notifier)",
    )
