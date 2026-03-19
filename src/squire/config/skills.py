"""Skills configuration.

Loaded from [skills] section in squire.toml and/or SQUIRE_SKILLS_ env vars.
"""

from functools import partial
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .loader import TomlSectionSource, get_section


class SkillsConfig(BaseSettings):
    """Configuration for file-based skills (Open Agent Skills spec)."""

    model_config = SettingsConfigDict(env_prefix="SQUIRE_SKILLS_", case_sensitive=False, extra="ignore")

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
            TomlSectionSource(settings_cls, partial(get_section, "skills")),
            file_secret_settings,
        )

    path: Path = Field(
        default=Path.home() / ".local" / "share" / "squire" / "skills",
        description="Directory containing skill definitions (each in a NAME/SKILL.md subdirectory)",
    )
