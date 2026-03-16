"""Watch mode configuration.

Loaded from [watch] section in squire.toml and/or SQUIRE_WATCH_ env vars.
"""

from functools import partial
from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .app import RiskThreshold, _coerce_risk_threshold
from .loader import TomlSectionSource, get_section


class WatchConfig(BaseSettings):
    """Configuration for autonomous watch mode (``squire watch``).

    Watch mode runs headless — no TUI, no interactive approval. Tools above
    the risk threshold are denied outright and a notification is dispatched.
    """

    model_config = SettingsConfigDict(env_prefix="SQUIRE_WATCH_", case_sensitive=False, extra="ignore")

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
            TomlSectionSource(settings_cls, partial(get_section, "watch")),
            file_secret_settings,
        )

    interval_minutes: int = Field(
        default=5,
        ge=1,
        description="Minutes between watch cycles",
    )
    risk_threshold: Annotated[RiskThreshold, BeforeValidator(_coerce_risk_threshold)] = Field(
        default=RiskThreshold.READ_ONLY,
        description="Risk threshold for watch mode (conservative default)",
    )
    risk_strict: bool = Field(
        default=True,
        description="Deny (not prompt) for tools above threshold — always True in watch mode",
    )
    max_tool_calls_per_cycle: int = Field(
        default=15,
        ge=1,
        description="Maximum tool calls allowed per watch cycle",
    )
    cycle_timeout_seconds: int = Field(
        default=300,
        ge=30,
        description="Maximum wall-clock time per watch cycle",
    )
    checkin_prompt: str = Field(
        default=(
            "Perform a routine check-in. Review the current system state "
            "and take action on anything that needs attention. Report your "
            "findings concisely."
        ),
        description="Prompt injected each watch cycle",
    )
    notify_on_action: bool = Field(
        default=True,
        description="Dispatch a notification when the agent takes a corrective action",
    )
    notify_on_blocked: bool = Field(
        default=True,
        description="Dispatch a notification when a tool call is blocked by the risk policy",
    )
    cycles_per_session: int = Field(
        default=50,
        ge=1,
        description="Rotate ADK session after this many cycles to bound memory",
    )
    allow: list[str] = Field(
        default_factory=list,
        description="Tool names that are always auto-allowed in watch mode",
    )
    deny: list[str] = Field(
        default_factory=list,
        description="Tool names that are always denied in watch mode",
    )
