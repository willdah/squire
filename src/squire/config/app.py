from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_top_level


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
        return (init_settings, env_settings, dotenv_settings, TomlSectionSource(settings_cls, get_top_level), file_secret_settings)

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
    risk_profile: str = Field(
        default="cautious",
        description="Risk profile controlling tool permissions: read-only, cautious, standard, full-trust, custom",
    )
    custom_allowed_tools: list[str] = Field(
        default_factory=list,
        description="Tools auto-allowed when risk_profile=custom",
    )
    custom_approval_tools: list[str] = Field(
        default_factory=list,
        description="Tools requiring approval when risk_profile=custom",
    )
    custom_denied_tools: list[str] = Field(
        default_factory=list,
        description="Tools denied when risk_profile=custom",
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
