from functools import partial

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section


class PathsConfig(BaseSettings):
    """Path and command allowlist/denylist configuration.

    Loaded from [paths] section in renew.toml and/or RENEW_PATHS_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_PATHS_", case_sensitive=False, extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, dotenv_settings, TomlSectionSource(settings_cls, partial(get_section, "paths")), file_secret_settings)

    config_allowlist: list[str] = Field(
        default_factory=list,
        description="Directory paths that read_config is allowed to access",
    )
    command_allowlist: list[str] = Field(
        default_factory=lambda: [
            "ping",
            "traceroute",
            "dig",
            "nslookup",
            "df",
            "free",
            "uptime",
            "ip",
            "ss",
            "cat",
            "head",
            "tail",
        ],
        description="Commands that run_command is allowed to execute",
    )
    command_denylist: list[str] = Field(
        default_factory=lambda: [
            "rm",
            "mkfs",
            "dd",
            "fdisk",
            "parted",
            "shutdown",
            "reboot",
            "init",
        ],
        description="Commands that are explicitly denied (checked first)",
    )
