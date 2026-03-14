from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LLM provider configuration.

    Environment variables use the prefix RENEW_LLM_.
    Example: RENEW_LLM_MODEL=anthropic/claude-sonnet-4-20250514
    """

    model_config = SettingsConfigDict(env_prefix="RENEW_LLM_", case_sensitive=False, extra="ignore")

    model: str = Field(
        default="ollama_chat/llama3.1:8b",
        description="LiteLLM model identifier (e.g., ollama_chat/llama3.1:8b, gemini/gemini-2.0-flash)",
    )
    api_base: str | None = Field(
        default=None,
        description="Optional API base URL (e.g., http://localhost:11434 for Ollama)",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for LLM responses",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Maximum tokens in LLM response",
    )
