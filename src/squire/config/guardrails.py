"""Guardrails configuration — consolidated tool, risk, and watch overrides.

Loaded from [guardrails] section in squire.toml and/or SQUIRE_GUARDRAILS_ env vars.
Replaces the old [security] and [risk] sections.
"""

from functools import partial
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .app import RiskTolerance, _coerce_risk_tolerance
from .loader import TomlSectionSource, get_section


class GuardrailsConfig(BaseSettings):
    """Consolidated guardrails: tool overrides, argument guards, per-agent tolerances, and watch-mode overrides.

    Loaded from [guardrails] section in squire.toml and/or SQUIRE_GUARDRAILS_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="SQUIRE_GUARDRAILS_", case_sensitive=False, extra="ignore")

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
            TomlSectionSource(settings_cls, partial(get_section, "guardrails")),
            file_secret_settings,
        )

    # --- Global risk policy ---

    risk_tolerance: Annotated[RiskTolerance, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=RiskTolerance.CAUTIOUS,
        description="Risk tolerance (1-5 or alias: read-only, cautious, standard, full-trust)",
    )
    risk_strict: bool = Field(
        default=False,
        description="When true, tools above tolerance are denied outright instead of prompting for approval",
    )

    # --- Tool-level overrides ---

    tools_allow: list[str] = Field(
        default_factory=list,
        description="Tool names that bypass risk check and auto-run",
    )
    tools_require_approval: list[str] = Field(
        default_factory=list,
        description="Tool names that always require user approval",
    )
    tools_deny: list[str] = Field(
        default_factory=list,
        description="Tool names that are hard-blocked, never run",
    )
    tools_risk_overrides: dict[str, int] = Field(
        default_factory=dict,
        description="Per-tool risk level overrides (tool name or tool:action -> 1-5)",
    )

    # --- Per-agent tolerance overrides ---

    monitor_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Monitor (falls back to global risk_tolerance)",
    )
    container_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Container (falls back to global risk_tolerance)",
    )
    admin_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Admin (falls back to global risk_tolerance)",
    )
    notifier_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Per-agent risk tolerance for Notifier (falls back to global risk_tolerance)",
    )

    # --- run_command argument guards ---

    commands_allow: list[str] = Field(
        default_factory=lambda: [
            # File / directory listing
            "ls",
            "stat",
            "file",
            "du",
            "find",
            "wc",
            # Text reading
            "cat",
            "head",
            "tail",
            "grep",
            # System info
            "hostname",
            "date",
            "whoami",
            "id",
            "uname",
            "uptime",
            "df",
            "free",
            "mount",
            "lsblk",
            "top",
            "ps",
            "which",
            # Network diagnostics
            "ping",
            "traceroute",
            "dig",
            "nslookup",
            "ip",
            "ss",
            "netstat",
            # Service management (read-only actions guarded by risk levels)
            "docker",
            "systemctl",
            "journalctl",
            "lsof",
        ],
        description="Commands that run_command is allowed to execute",
    )
    commands_block: list[str] = Field(
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
        description="Commands that are explicitly blocked (checked first)",
    )

    # --- read_config path guards ---

    config_paths: list[str] = Field(
        default_factory=list,
        description="Directory paths that read_config is allowed to access",
    )

    # --- Watch-mode overrides (from [guardrails.watch] sub-table) ---

    watch_tolerance: Annotated[RiskTolerance | None, BeforeValidator(_coerce_risk_tolerance)] = Field(
        default=None,
        description="Risk tolerance override for watch mode (falls back to global risk_tolerance)",
    )
    watch_tools_allow: list[str] = Field(
        default_factory=list,
        description="Additional tools to auto-allow in watch mode",
    )
    watch_tools_deny: list[str] = Field(
        default_factory=list,
        description="Additional tools to deny in watch mode",
    )
