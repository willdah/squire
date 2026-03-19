"""Watch mode configuration.

Loaded from [watch] section in squire.toml and/or SQUIRE_WATCH_ env vars.
Risk policy for watch mode is now in [guardrails.watch].
"""

from functools import partial

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section


class WatchConfig(BaseSettings):
    """Operational configuration for autonomous watch mode (``squire watch``).

    Watch mode runs headless — no TUI, no interactive approval. Risk policy
    (tolerance, tool allow/deny) is configured under ``[guardrails.watch]``.
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
