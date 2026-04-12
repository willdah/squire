"""Tests for SkillService — file-based skill CRUD."""

import pytest
from pydantic import ValidationError

from squire.skills import Skill, SkillService


@pytest.fixture
def skill_service(tmp_path):
    """Provide a SkillService backed by a temporary directory."""
    return SkillService(tmp_path)


def _make_skill(**kwargs) -> Skill:
    """Create a Skill with sensible defaults."""
    defaults = {
        "name": "test-skill",
        "description": "A test skill",
        "hosts": ["all"],
        "trigger": "manual",
        "enabled": True,
        "incident_keys": [],
        "instructions": "Check the status of all containers.",
    }
    defaults.update(kwargs)
    return Skill(**defaults)


class TestSaveAndGet:
    def test_roundtrip(self, skill_service):
        skill = _make_skill()
        skill_service.save_skill(skill)
        loaded = skill_service.get_skill("test-skill")
        assert loaded is not None
        assert loaded.name == "test-skill"
        assert loaded.description == "A test skill"
        assert loaded.hosts == ["all"]
        assert loaded.trigger == "manual"
        assert loaded.enabled is True
        assert loaded.instructions == "Check the status of all containers."

    def test_get_not_found(self, skill_service):
        assert skill_service.get_skill("nonexistent") is None

    def test_overwrite(self, skill_service):
        skill = _make_skill(description="v1")
        skill_service.save_skill(skill)
        updated = skill.model_copy(update={"description": "v2"})
        skill_service.save_skill(updated)
        loaded = skill_service.get_skill("test-skill")
        assert loaded.description == "v2"


class TestListSkills:
    def test_empty_dir(self, skill_service):
        assert skill_service.list_skills() == []

    def test_nonexistent_dir(self, tmp_path):
        service = SkillService(tmp_path / "does-not-exist")
        assert service.list_skills() == []

    def test_list_all(self, skill_service):
        skill_service.save_skill(_make_skill(name="alpha"))
        skill_service.save_skill(_make_skill(name="beta"))
        skills = skill_service.list_skills()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"alpha", "beta"}

    def test_filter_enabled_only(self, skill_service):
        skill_service.save_skill(_make_skill(name="on", enabled=True))
        skill_service.save_skill(_make_skill(name="off", enabled=False))
        enabled = skill_service.list_skills(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "on"

    def test_filter_trigger(self, skill_service):
        skill_service.save_skill(_make_skill(name="manual-skill", trigger="manual"))
        skill_service.save_skill(_make_skill(name="watch-skill", trigger="watch"))
        watch = skill_service.list_skills(trigger="watch")
        assert len(watch) == 1
        assert watch[0].name == "watch-skill"

    def test_combined_filters(self, skill_service):
        skill_service.save_skill(_make_skill(name="a", trigger="watch", enabled=True))
        skill_service.save_skill(_make_skill(name="b", trigger="watch", enabled=False))
        skill_service.save_skill(_make_skill(name="c", trigger="manual", enabled=True))
        result = skill_service.list_skills(enabled_only=True, trigger="watch")
        assert len(result) == 1
        assert result[0].name == "a"


class TestDeleteSkill:
    def test_delete_existing(self, skill_service):
        skill_service.save_skill(_make_skill(name="to-delete"))
        assert skill_service.delete_skill("to-delete") is True
        assert skill_service.get_skill("to-delete") is None

    def test_delete_not_found(self, skill_service):
        assert skill_service.delete_skill("ghost") is False


class TestParsing:
    def test_malformed_frontmatter_skipped_in_list(self, skill_service, tmp_path):
        """A directory with a malformed SKILL.md is silently skipped."""
        bad_dir = tmp_path / "bad-skill"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("no frontmatter here")
        skills = skill_service.list_skills()
        assert len(skills) == 0

    def test_missing_name_uses_directory(self, skill_service, tmp_path):
        """If name is missing from frontmatter, use directory name."""
        skill_dir = tmp_path / "dir-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\n\nDo something.")
        skill = skill_service.get_skill("dir-name")
        assert skill is not None
        assert skill.name == "dir-name"
        assert skill.instructions == "Do something."

    def test_multiline_instructions(self, skill_service):
        instructions = "Step 1: Check containers.\n\nStep 2: Restart if needed.\n\n- Item A\n- Item B"
        skill = _make_skill(instructions=instructions)
        skill_service.save_skill(skill)
        loaded = skill_service.get_skill("test-skill")
        assert loaded.instructions == instructions

    def test_metadata_roundtrip(self, skill_service):
        """Squire-specific fields survive a save/load cycle via metadata."""
        skill = _make_skill(hosts=["prod-01"], trigger="watch", enabled=False, incident_keys=["disk-pressure:"])
        skill_service.save_skill(skill)
        loaded = skill_service.get_skill("test-skill")
        assert loaded.hosts == ["prod-01"]
        assert loaded.trigger == "watch"
        assert loaded.enabled is False
        assert loaded.incident_keys == ["disk-pressure:"]

    def test_default_metadata_omitted(self, skill_service, tmp_path):
        """When hosts/trigger/enabled are defaults, metadata key is omitted."""
        skill = _make_skill()
        skill_service.save_skill(skill)
        content = (tmp_path / "test-skill" / "SKILL.md").read_text()
        assert "metadata:" not in content

    def test_spec_compliant_frontmatter(self, skill_service, tmp_path):
        """Rendered SKILL.md has name/description at top level, custom fields under metadata."""
        skill = _make_skill(hosts=["nas"], trigger="watch")
        skill_service.save_skill(skill)
        content = (tmp_path / "test-skill" / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: test-skill\n" in content
        assert "description: A test skill\n" in content
        assert "metadata:\n" in content
        assert "  hosts:\n" in content
        assert "  - nas\n" in content
        assert "  trigger: watch\n" in content

    def test_legacy_host_metadata_is_retrofitted_to_hosts(self, skill_service, tmp_path):
        skill_dir = tmp_path / "legacy-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: legacy-skill\n"
            "description: legacy\n"
            "metadata:\n"
            "  host: remote-1\n"
            "  trigger: watch\n"
            "---\n\n"
            "Run checks."
        )
        loaded = skill_service.get_skill("legacy-skill")
        assert loaded is not None
        assert loaded.hosts == ["remote-1"]


class TestNameValidation:
    def test_valid_names(self):
        for name in ("a", "abc", "my-skill", "check-containers-v2", "a1b2"):
            Skill(name=name, description="test")

    def test_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="My-Skill", description="test")

    def test_leading_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="-bad", description="test")

    def test_trailing_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="bad-", description="test")

    def test_consecutive_hyphens_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="bad--name", description="test")

    def test_spaces_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="bad name", description="test")

    def test_too_long_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="a" * 65, description="test")

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            Skill(name="", description="test")
