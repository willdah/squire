from enum import StrEnum
from functools import partial
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section, get_top_level


class RiskThreshold(StrEnum):
    """Named risk-threshold aliases accepted in config and env vars."""

    READ_ONLY = "read-only"
    CAUTIOUS = "cautious"
    STANDARD = "standard"
    FULL_TRUST = "full-trust"


_INT_TO_ALIAS: dict[int, str] = {1: "read-only", 2: "cautious", 3: "standard", 5: "full-trust"}


def _coerce_risk_threshold(value: Any) -> str:
    """Accept int (1-3, 5) or string alias; normalise to a RiskThreshold value."""
    if isinstance(value, int):
        if value in _INT_TO_ALIAS:
            return _INT_TO_ALIAS[value]
        raise ValueError(f"No alias for numeric threshold {value}; valid: {list(_INT_TO_ALIAS.keys())}")
    if isinstance(value, str) and value.isdigit():
        return _coerce_risk_threshold(int(value))
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
    risk_threshold: Annotated[RiskThreshold, BeforeValidator(_coerce_risk_threshold)] = Field(
        default=RiskThreshold.CAUTIOUS,
        description="Risk threshold (1-5 or alias: read-only, cautious, standard, full-trust)",
    )
    risk_strict: bool = Field(
        default=False,
        description="When true, tools above threshold are denied outright instead of prompting for approval",
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
        description="Tool names that are always auto-allowed regardless of threshold",
    )
    approve: list[str] = Field(
        default_factory=list,
        description="Tool names that always require approval even if threshold would allow",
    )
    deny: list[str] = Field(
        default_factory=list,
        description="Tool names that are always denied",
    )
