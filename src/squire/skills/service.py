"""SkillService — file-based CRUD for SKILL.md directories.

Each skill lives in its own directory under the configured skills path:

    skills/
      restart-on-error/
        SKILL.md

SKILL.md uses YAML frontmatter + freeform Markdown body (Open Agent Skills spec).
Squire-specific fields (host, trigger, enabled) are stored under the ``metadata``
key to stay spec-compliant.
"""

import re
import shutil
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

# Spec: lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens, max 64 chars.
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class Skill(BaseModel):
    """A single skill definition parsed from a SKILL.md file."""

    name: str
    description: str = ""
    host: str = "all"
    trigger: str = "manual"  # "manual" | "watch"
    enabled: bool = True
    instructions: str = ""  # freeform Markdown body

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) > 64:
            raise ValueError("name must be 1-64 characters")
        if "--" in v:
            raise ValueError("name must not contain consecutive hyphens")
        if not _NAME_RE.match(v):
            raise ValueError("name must be lowercase letters, numbers, and hyphens only (no leading/trailing hyphens)")
        return v


class SkillService:
    """File-based skill CRUD backed by SKILL.md directories."""

    def __init__(self, skills_dir: Path) -> None:
        self._dir = skills_dir

    def list_skills(self, *, enabled_only: bool = False, trigger: str | None = None) -> list[Skill]:
        """List all skills, optionally filtered by enabled state and trigger type."""
        if not self._dir.is_dir():
            return []

        skills: list[Skill] = []
        for child in sorted(self._dir.iterdir()):
            skill_file = child / "SKILL.md"
            if not child.is_dir() or not skill_file.is_file():
                continue
            try:
                skill = self._parse_skill_md(skill_file)
            except Exception:
                continue
            if enabled_only and not skill.enabled:
                continue
            if trigger and skill.trigger != trigger:
                continue
            skills.append(skill)
        return skills

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name. Returns None if not found."""
        skill_file = self._dir / name / "SKILL.md"
        if not skill_file.is_file():
            return None
        try:
            return self._parse_skill_md(skill_file)
        except Exception:
            return None

    def save_skill(self, skill: Skill) -> Path:
        """Create or update a skill directory with SKILL.md. Returns the file path."""
        skill_dir = self._dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(self._render_skill_md(skill))
        return skill_file

    def delete_skill(self, name: str) -> bool:
        """Delete a skill directory. Returns True if it existed."""
        skill_dir = self._dir / name
        if not skill_dir.is_dir():
            return False
        shutil.rmtree(skill_dir)
        return True

    def _parse_skill_md(self, path: Path) -> Skill:
        """Parse a SKILL.md file into a Skill model."""
        content = path.read_text()
        if not content.startswith("---"):
            raise ValueError(f"Missing YAML frontmatter in {path}")

        # Split frontmatter from body
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter format in {path}")

        frontmatter = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()

        # Directory name is the canonical slug
        dir_name = path.parent.name

        # Squire-specific fields live under metadata (spec-compliant)
        meta = frontmatter.get("metadata") or {}

        return Skill(
            name=frontmatter.get("name", dir_name),
            description=frontmatter.get("description", ""),
            host=meta.get("host", "all"),
            trigger=meta.get("trigger", "manual"),
            enabled=meta.get("enabled", True),
            instructions=body,
        )

    def _render_skill_md(self, skill: Skill) -> str:
        """Serialize a Skill model back to SKILL.md format.

        Produces spec-compliant frontmatter: ``name`` and ``description`` at
        the top level, Squire-specific fields under ``metadata``.
        """
        frontmatter: dict = {
            "name": skill.name,
            "description": skill.description,
        }
        metadata: dict = {}
        if skill.host != "all":
            metadata["host"] = skill.host
        if skill.trigger != "manual":
            metadata["trigger"] = skill.trigger
        if not skill.enabled:
            metadata["enabled"] = skill.enabled
        if metadata:
            frontmatter["metadata"] = metadata
        fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{fm_str}\n---\n\n{skill.instructions}\n"
