from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database persistence configuration.

    Environment variables use the prefix RENEW_DB_.
    Example: RENEW_DB_PATH=~/.local/share/renew/renew.db
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_DB_", case_sensitive=False, extra="ignore")

    path: Path = Field(
        default=Path.home() / ".local" / "share" / "renew" / "renew.db",
        description="Path to the SQLite database file",
    )
    snapshot_interval_minutes: int = Field(
        default=15,
        ge=1,
        description="Minutes between automatic system snapshots",
    )
