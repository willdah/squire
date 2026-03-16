from enum import StrEnum
from functools import partial
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section, get_top_level


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
            TomlSectionSource(settings_cls, get_top_level),
            file_secret_settings,
        )

    app_name: str = Field(
        default="Squire",
        description="Application name passed to the ADK runner",
    )
    user_id: str = Field(
        default="squire-user",
        description="User ID for ADK session management",
    )
    house: str = Field(
        default="",
        description="Name of the house this Squire serves (e.g. a family name, crest, or domain)",
    )
    squire_name: str = Field(
        default="",
        description="Custom name for your Squire — overrides the profile's bundled name if set",
    )
    squire_profile: str = Field(
        default="",
        description="Pre-configured Squire profile: rook, cedric, wynn",
    )
    risk_tolerance: Annotated[RiskTolerance, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=RiskTolerance.CAUTIOUS,
        description="Risk tolerance (1-5 or alias: read-only, cautious, standard, full-trust)",
    )
    risk_strict: bool = Field(
        default=False,
        description="When true, tools above tolerance are denied outright instead of prompting for approval",
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
    monitor_risk_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Monitor (falls back to global risk_tolerance)",
    )
    container_risk_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Container (falls back to global risk_tolerance)",
    )
    admin_risk_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Admin (falls back to global risk_tolerance)",
    )
    notifier_risk_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Notifier (falls back to global risk_tolerance)",
    )


class RiskOverridesConfig(BaseSettings):
    """Per-tool risk overrides from [risk] section in squire.toml."""

    model_config = SettingsConfigDict(env_prefix="SQUIRE_RISK_", case_sensitive=False, extra="ignore")

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
            TomlSectionSource(settings_cls, partial(get_section, "risk")),
            file_secret_settings,
        )

    allow: list[str] = Field(
        default_factory=list,
        description="Tool names that are always auto-allowed regardless of tolerance",
    )
    approve: list[str] = Field(
        default_factory=list,
        description="Tool names that always require approval even if tolerance would allow",
    )
    deny: list[str] = Field(
        default_factory=list,
        description="Tool names that are always denied",
    )
