"""SkillService — file-based CRUD for SKILL.md directories.

Each skill lives in its own directory under the configured skills path:

    skills/
      restart-on-error/
        SKILL.md

SKILL.md uses YAML frontmatter + freeform Markdown body (Open Agent Skills spec).
Squire-specific fields (hosts, trigger, enabled, incident_keys) are stored under
the ``metadata`` key to stay spec-compliant.
"""

import re
import shutil
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

Effect = Literal["read", "write", "mixed"]
Autonomy = Literal["observe", "remediate", "propose"]

# Spec: lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens, max 64 chars.
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class Skill(BaseModel):
    """A single skill definition parsed from a SKILL.md file."""

    name: str
    description: str = ""
    hosts: list[str] = Field(default_factory=lambda: ["all"])
    trigger: str = "manual"  # "manual" | "watch"
    enabled: bool = True
    incident_keys: list[str] = Field(default_factory=list)
    effect: Effect = "mixed"  # what the skill does to system state
    autonomy: Autonomy = "propose"  # default — force approval even in autonomous mode
    allowed_tools: list[str] = Field(default_factory=list)
    category: str | None = None  # reliability | maintenance | security | design
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

    @field_validator("hosts", mode="before")
    @classmethod
    def validate_hosts(cls, value) -> list[str]:
        if value is None:
            return ["all"]
        if isinstance(value, str):
            value = [value]
        hosts = [str(v).strip() for v in value if str(v).strip()]
        if not hosts:
            return ["all"]
        if "all" in hosts:
            return ["all"]
        return sorted(set(hosts))

    @field_validator("incident_keys", mode="before")
    @classmethod
    def validate_incident_keys(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        keys = [str(v).strip() for v in value if str(v).strip()]
        return sorted(set(keys))


class SkillService:
    """File-based skill CRUD backed by SKILL.md directories."""

    def __init__(self, skills_dir: Path) -> None:
        self._dir = skills_dir

    def _resolve_skill_dir(self, name: str) -> Path | None:
        """Find the directory containing SKILL.md for a user-supplied slug or declared name.

        Lookup order:

        1. Exact directory name under ``skills_dir`` (spec slug).
        2. Case-insensitive directory name match (helps macOS / human-entered URLs).
        3. Declared ``name`` in SKILL.md frontmatter (directory slug may differ).
        """
        key = name.strip()
        if not key:
            return None
        if not self._dir.is_dir():
            return None

        key_cf = key.casefold()
        exact_dir: Path | None = None
        case_dir: Path | None = None
        for child in sorted(self._dir.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.is_file():
                continue
            if child.name == key:
                exact_dir = child
            elif child.name.casefold() == key_cf:
                case_dir = child

        # Prefer the real directory entry name (correct casing for parsing on
        # case-insensitive volumes) over constructing ``_dir / key``.
        if exact_dir is not None:
            return exact_dir
        if case_dir is not None:
            return case_dir

        for child in sorted(self._dir.iterdir()):
            skill_file = child / "SKILL.md"
            if not child.is_dir() or not skill_file.is_file():
                continue
            try:
                skill = self._parse_skill_md(skill_file)
            except Exception:
                continue
            if skill.name == key or skill.name.casefold() == key_cf:
                return child

        return None

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
        """Get a skill by directory slug or declared frontmatter ``name``."""
        skill_dir = self._resolve_skill_dir(name)
        if skill_dir is None:
            return None
        try:
            return self._parse_skill_md(skill_dir / "SKILL.md")
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
        skill_dir = self._resolve_skill_dir(name)
        if skill_dir is None or not skill_dir.is_dir():
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
        hosts = meta.get("hosts")
        if hosts is None and "host" in meta:
            # Legacy retrofit: host -> hosts
            hosts = [meta.get("host", "all")]

        return Skill(
            name=frontmatter.get("name", dir_name),
            description=frontmatter.get("description", ""),
            hosts=hosts if hosts is not None else ["all"],
            trigger=meta.get("trigger", "manual"),
            enabled=meta.get("enabled", True),
            incident_keys=meta.get("incident_keys", []),
            effect=meta.get("effect", "mixed"),
            autonomy=meta.get("autonomy", "propose"),
            allowed_tools=meta.get("allowed_tools", []),
            category=meta.get("category"),
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
        if skill.hosts != ["all"]:
            metadata["hosts"] = skill.hosts
        if skill.trigger != "manual":
            metadata["trigger"] = skill.trigger
        if not skill.enabled:
            metadata["enabled"] = skill.enabled
        if skill.incident_keys:
            metadata["incident_keys"] = skill.incident_keys
        if skill.effect != "mixed":
            metadata["effect"] = skill.effect
        if skill.autonomy != "propose":
            metadata["autonomy"] = skill.autonomy
        if skill.allowed_tools:
            metadata["allowed_tools"] = skill.allowed_tools
        if skill.category:
            metadata["category"] = skill.category
        if metadata:
            frontmatter["metadata"] = metadata
        fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{fm_str}\n---\n\n{skill.instructions}\n"
