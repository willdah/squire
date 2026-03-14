from functools import partial

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section


class SecurityConfig(BaseSettings):
    """Tool security allow/deny lists for commands and config paths.

    Loaded from [security] section in squire.toml and/or SQUIRE_SECURITY_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="SQUIRE_SECURITY_", case_sensitive=False, extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, dotenv_settings, TomlSectionSource(settings_cls, partial(get_section, "security")), file_secret_settings)

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
            # Shell interpreters and scripting runtimes — prevent shell escape
            "bash",
            "sh",
            "zsh",
            "fish",
            "csh",
            "tcsh",
            "dash",
            "python",
            "python3",
            "perl",
            "ruby",
            "node",
            "lua",
        ],
        description="Commands that are explicitly denied (checked first)",
    )
