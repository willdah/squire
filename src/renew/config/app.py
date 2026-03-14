from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Top-level application configuration.

    Environment variables use the prefix RENEW_.
    Example: RENEW_RISK_PROFILE=cautious
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_", case_sensitive=False, extra="ignore")

    app_name: str = Field(
        default="Renew",
        description="Application name passed to the ADK runner",
    )
    user_id: str = Field(
        default="renew-user",
        description="User ID for ADK session management",
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
