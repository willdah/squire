from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class NotificationsConfig(BaseSettings):
    """Notification system configuration.

    Environment variables use the prefix RENEW_NOTIFICATIONS_.
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_NOTIFICATIONS_", case_sensitive=False, extra="ignore")

    enabled: bool = Field(
        default=False,
        description="Whether notifications are enabled",
    )
    webhooks: list[WebhookConfig] = Field(
        default_factory=list,
        description="List of webhook endpoints to send notifications to",
    )
