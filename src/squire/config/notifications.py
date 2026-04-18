from functools import partial

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .db_source import DatabaseOverrideSource
from .loader import TomlSectionSource, get_section


class WebhookConfig(BaseModel):
    """Configuration for a single webhook notification endpoint."""

    name: str = Field(description="Human-readable name for this webhook (e.g., 'discord', 'ntfy')")
    url: str = Field(description="Webhook URL to POST events to")
    events: list[str] = Field(
        default=["*"],
        description="Event categories to send (e.g., 'error', 'approval_denied', or '*' for all)",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional HTTP headers (e.g., Authorization)",
    )


class EmailConfig(BaseModel):
    """Configuration for email notification delivery."""

    enabled: bool = Field(default=False, description="Whether email notifications are enabled")
    smtp_host: str = Field(default="", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP port (typically 587 for TLS)")
    use_tls: bool = Field(default=True, description="Use STARTTLS for SMTP connection")
    smtp_user: str = Field(default="", description="SMTP authentication username")
    smtp_password: str = Field(default="", description="SMTP authentication password")
    from_address: str = Field(default="", description="Email sender address")
    to_addresses: list[str] = Field(default_factory=list, description="Recipient email addresses")
    events: list[str] = Field(default=["*"], description="Event categories to send (or '*' for all)")


class NotificationsConfig(BaseSettings):
    """Notification system configuration.

    Loaded from [notifications] section in squire.toml and/or SQUIRE_NOTIFICATIONS_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="SQUIRE_NOTIFICATIONS_", case_sensitive=False, extra="ignore")

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
            DatabaseOverrideSource(settings_cls, "notifications"),
            TomlSectionSource(settings_cls, partial(get_section, "notifications", preserve={"email"})),
            file_secret_settings,
        )

    enabled: bool = Field(
        default=False,
        description="Whether notifications are enabled",
    )
    webhooks: list[WebhookConfig] = Field(
        default_factory=list,
        description="List of webhook endpoints to send notifications to",
    )
    email: EmailConfig | None = Field(
        default=None,
        description="Email notification configuration",
    )
