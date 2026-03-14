from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PathsConfig(BaseSettings):
    """Path and command allowlist/denylist configuration.

    Environment variables use the prefix RENEW_PATHS_.
    Lists can be set as comma-separated values:
    Example: RENEW_PATHS_CONFIG_ALLOWLIST=/etc/nginx/,/opt/stacks/
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_PATHS_", case_sensitive=False, extra="ignore")

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
