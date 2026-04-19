"""Tests for the scheduled + skill-driven insight sweep."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squire.insight_sweep import (
    _VALID_CATEGORIES,
    parse_skill_insights,
    run_insight_sweep,
)
from squire.skills.service import Skill, SkillService

# --- Parser --------------------------------------------------------------


def test_parser_extracts_multiple_insights():
    response = """
    Here's what I observed:
    INSIGHT: severity=high summary="Backup failed on web-01" host="web-01"
    INSIGHT: severity=low summary="Disk trending toward full in 6 weeks"
    Thanks!
    """
    out = parse_skill_insights(response, default_category="reliability")
    assert len(out) == 2
    assert out[0]["severity"] == "high"
    assert out[0]["summary"] == "Backup failed on web-01"
    assert out[0]["host"] == "web-01"
    assert out[1]["severity"] == "low"
    assert out[1]["summary"] == "Disk trending toward full in 6 weeks"
    assert out[1]["host"] is None


def test_parser_uses_default_category_when_missing():
    response = 'INSIGHT: severity=medium summary="Generic observation"'
    out = parse_skill_insights(response, default_category="security")
    assert out[0]["category"] == "security"


def test_parser_respects_explicit_category_override():
    response = 'INSIGHT: severity=medium summary="x" category=maintenance'
    out = parse_skill_insights(response, default_category="security")
    assert out[0]["category"] == "maintenance"


def test_parser_ignores_invalid_severity():
    response = 'INSIGHT: severity=yolo summary="x"'
    assert parse_skill_insights(response, default_category="reliability") == []


def test_parser_ignores_invalid_category():
    response = 'INSIGHT: severity=low summary="x" category=bogus'
    out = parse_skill_insights(response, default_category="design")
    # Falls back to default when category is not recognized.
    assert out[0]["category"] == "design"


def test_parser_ignores_missing_summary():
    response = "INSIGHT: severity=low"
    assert parse_skill_insights(response, default_category="reliability") == []


def test_parser_is_case_insensitive_on_prefix():
    response = 'insight: severity=high summary="Case test"'
    out = parse_skill_insights(response, default_category="reliability")
    assert len(out) == 1


def test_parser_strips_markdown_list_markers():
    response = '- INSIGHT: severity=medium summary="bulleted"\n* INSIGHT: severity=low summary="starred"'
    out = parse_skill_insights(response, default_category="reliability")
    assert len(out) == 2


def test_parser_unquoted_values_terminate_at_next_key():
    response = "INSIGHT: severity=low summary=short_summary host=web-01"
    out = parse_skill_insights(response, default_category="reliability")
    assert len(out) == 1
    assert out[0]["summary"] == "short_summary"
    assert out[0]["host"] == "web-01"


def test_known_categories_are_locked():
    # Regression guard — if someone adds/removes a tab, keep the set authoritative.
    assert _VALID_CATEGORIES == frozenset({"reliability", "maintenance", "security", "design"})


# --- End-to-end sweep with a stubbed runner ------------------------------


class _FakeAdkRuntime:
    """Stub ADK runtime that captures sessions and returns a canned response."""

    def __init__(self, response_text: str):
        self._response = response_text
        self.created_runners = 0

    def create_runner(self, *, app):
        self.created_runners += 1
        runtime = self

        class _FakeRunner:
            async def run_async(self, *, user_id, session_id, new_message):
                # Emit one event with the canned text.
                class _Part:
                    text = runtime._response
                    function_call = None
                    thought = False

                class _Content:
                    parts = [_Part()]

                class _Event:
                    content = _Content()

                yield _Event()

        return _FakeRunner()

    async def get_or_create_session(self, *, app_name, user_id, session_id, state):
        class _Session:
            id = session_id

        return _Session()


@pytest.mark.asyncio
async def test_run_insight_sweep_runs_observe_skills_with_category(db, monkeypatch):
    # Silence the metric rules for this test — we only care about skill-driven here.
    monkeypatch.setattr("squire.watch_autonomy.insight_sweep_from_metrics", AsyncMock(return_value=0))

    with tempfile.TemporaryDirectory() as tmp:
        skills_dir = Path(tmp)
        (skills_dir / "exposed-ports").mkdir()
        (skills_dir / "exposed-ports" / "SKILL.md").write_text(
            "---\n"
            "name: exposed-ports\n"
            "description: check for exposed services\n"
            "metadata:\n"
            "  trigger: watch\n"
            "  autonomy: observe\n"
            "  category: security\n"
            "---\n\n"
            "Look for exposed ports on managed hosts.\n"
        )
        svc = SkillService(skills_dir)

        fake_response = (
            "Analysis complete.\n"
            'INSIGHT: severity=high summary="Port 22 exposed to 0.0.0.0" host="web-01"\n'
            'INSIGHT: severity=medium summary="Telnet service running"\n'
        )
        runtime = _FakeAdkRuntime(fake_response)

        class _LLMCfg:
            model = "fake/model"
            temperature = 0.0
            max_tokens = 100
            api_base = None

        class _AppCfg:
            user_id = "test-user"
            app_name = "squire-test"
            multi_agent = False

        result = await run_insight_sweep(
            db=db,
            skill_service=svc,
            adk_runtime=runtime,
            llm_config=_LLMCfg(),
            app_config=_AppCfg(),
        )

        assert result["skill_insights"] == 2
        rows = await db.list_insights(category="security")
        assert len(rows) == 2
        summaries = {r["summary"] for r in rows}
        assert "Port 22 exposed to 0.0.0.0" in summaries
        assert "Telnet service running" in summaries


@pytest.mark.asyncio
async def test_run_insight_sweep_skips_non_observe_skills(db, monkeypatch):
    monkeypatch.setattr("squire.watch_autonomy.insight_sweep_from_metrics", AsyncMock(return_value=0))

    with tempfile.TemporaryDirectory() as tmp:
        skills_dir = Path(tmp)
        svc = SkillService(skills_dir)
        # A remediate-tier skill should be ignored by the observe-only sweep.
        svc.save_skill(
            Skill(
                name="restart-skill",
                description="",
                autonomy="remediate",
                category="reliability",
                allowed_tools=[],
                instructions="Restart things.",
            )
        )

        runtime = _FakeAdkRuntime('INSIGHT: severity=high summary="should not fire"')

        class _LLMCfg:
            model = "fake/model"
            temperature = 0.0
            max_tokens = 100
            api_base = None

        class _AppCfg:
            user_id = "u"
            app_name = "a"
            multi_agent = False

        result = await run_insight_sweep(
            db=db,
            skill_service=svc,
            adk_runtime=runtime,
            llm_config=_LLMCfg(),
            app_config=_AppCfg(),
        )
        assert result["skill_insights"] == 0
        assert runtime.created_runners == 0


@pytest.mark.asyncio
async def test_run_insight_sweep_skips_observe_without_category(db, monkeypatch):
    monkeypatch.setattr("squire.watch_autonomy.insight_sweep_from_metrics", AsyncMock(return_value=0))

    with tempfile.TemporaryDirectory() as tmp:
        svc = SkillService(Path(tmp))
        svc.save_skill(
            Skill(
                name="plain-observer",
                autonomy="observe",
                category=None,
                instructions="Look at things.",
            )
        )
        runtime = _FakeAdkRuntime('INSIGHT: severity=low summary="x"')

        class _LLMCfg:
            model = "fake/model"
            temperature = 0.0
            max_tokens = 100
            api_base = None

        class _AppCfg:
            user_id = "u"
            app_name = "a"
            multi_agent = False

        result = await run_insight_sweep(
            db=db,
            skill_service=svc,
            adk_runtime=runtime,
            llm_config=_LLMCfg(),
            app_config=_AppCfg(),
        )
        assert result["skill_insights"] == 0
        assert runtime.created_runners == 0
