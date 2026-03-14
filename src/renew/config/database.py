from functools import partial
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section


class DatabaseConfig(BaseSettings):
    """Database persistence configuration.

    Loaded from [db] section in renew.toml and/or RENEW_DB_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_DB_", case_sensitive=False, extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, dotenv_settings, TomlSectionSource(settings_cls, partial(get_section, "db")), file_secret_settings)

    path: Path = Field(
        default=Path.home() / ".local" / "share" / "renew" / "renew.db",
        description="Path to the SQLite database file",
    )
    snapshot_interval_minutes: int = Field(
        default=15,
        ge=1,
        description="Minutes between automatic system snapshots",
    )
