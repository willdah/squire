"""Tests for skill execution completion marker parsing."""

from squire.api.routers.chat import _is_skill_complete


class TestIsSkillComplete:
    def test_marker_present(self):
        assert _is_skill_complete("Summary of results.\n[SKILL COMPLETE]") is True

    def test_marker_absent(self):
        assert _is_skill_complete("Still working on things.") is False

    def test_case_insensitive(self):
        assert _is_skill_complete("[skill complete]") is True
        assert _is_skill_complete("[Skill Complete]") is True

    def test_embedded_in_text(self):
        text = "All done. Here is the summary:\n- OK\n[SKILL COMPLETE]\n"
        assert _is_skill_complete(text) is True

    def test_extra_whitespace(self):
        assert _is_skill_complete("[SKILL  COMPLETE]") is True

    def test_partial_match_is_not_complete(self):
        assert _is_skill_complete("[SKILL") is False
        assert _is_skill_complete("SKILL COMPLETE") is False
