from functools import partial

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .db_source import DatabaseOverrideSource
from .loader import TomlSectionSource, get_section


class LLMConfig(BaseSettings):
    """LLM provider configuration.

    Loaded from [llm] section in squire.toml and/or SQUIRE_LLM_ env vars.
    Env vars take precedence over TOML values.
    """

    model_config = SettingsConfigDict(env_prefix="SQUIRE_LLM_", case_sensitive=False, extra="ignore")

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
            DatabaseOverrideSource(settings_cls, "llm"),
            TomlSectionSource(settings_cls, partial(get_section, "llm")),
            file_secret_settings,
        )

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
