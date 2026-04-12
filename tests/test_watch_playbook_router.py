"""Tests for dynamic watch playbook routing."""

import pytest

from squire.config import LLMConfig
from squire.skills import Skill
from squire.watch_autonomy import Incident
from squire.watch_playbooks.router import RouterThresholds, route_playbooks_for_incidents


def _skill(name: str, *, incident_keys: list[str], description: str, hosts: list[str] | None = None) -> Skill:
    return Skill(
        name=name,
        description=description,
        trigger="watch",
        hosts=hosts or ["all"],
        incident_keys=incident_keys,
        instructions=f"Instructions for {name}",
    )


@pytest.mark.asyncio
async def test_deterministic_single_selected():
    incident = Incident(
        key="disk-pressure:local", severity="high", title="Disk pressure", detail="95% used", host="local"
    )
    skills = [_skill("triage-disk", incident_keys=["disk-pressure:"], description="Handle disk pressure incidents")]

    prompt_playbooks, selections = await route_playbooks_for_incidents(incidents=[incident], playbook_skills=skills)

    assert selections[0].path_taken == "deterministic_single"
    assert selections[0].selected_playbook == "triage-disk"
    assert any("triage-disk" in block for block in prompt_playbooks)


@pytest.mark.asyncio
async def test_tie_break_low_confidence_falls_back_to_generic(monkeypatch):
    incident = Incident(
        key="container-unhealthy:local:api",
        severity="high",
        title="Container unhealthy",
        detail="api restarting",
        host="local",
    )
    skills = [
        _skill("candidate-a", incident_keys=["container-unhealthy:"], description="Container health"),
        _skill("candidate-b", incident_keys=["container-unhealthy:"], description="Container fallback"),
    ]

    async def _fake_choose(*args, **kwargs):
        return skills[0], 0.2, "not confident"

    monkeypatch.setattr("squire.watch_playbooks.router._llm_choose_best", _fake_choose)
    prompt_playbooks, selections = await route_playbooks_for_incidents(incidents=[incident], playbook_skills=skills)

    assert selections[0].path_taken == "generic"
    assert selections[0].selected_playbook is None
    assert any("Default Watch Triage" in block for block in prompt_playbooks)


@pytest.mark.asyncio
async def test_semantic_fallback_when_no_deterministic(monkeypatch):
    incident = Incident(
        key="unknown-incident:local", severity="medium", title="Unknown", detail="something odd", host="local"
    )
    skills = [_skill("semantic-choice", incident_keys=["disk-pressure:"], description="something odd pattern matcher")]

    async def _fake_choose(*args, **kwargs):
        return skills[0], 0.9, "semantic match"

    monkeypatch.setattr("squire.watch_playbooks.router._llm_choose_best", _fake_choose)
    prompt_playbooks, selections = await route_playbooks_for_incidents(incidents=[incident], playbook_skills=skills)

    assert selections[0].path_taken == "semantic"
    assert selections[0].selected_playbook == "semantic-choice"
    assert any("semantic-choice" in block for block in prompt_playbooks)


@pytest.mark.asyncio
async def test_playbook_merge_caps_selected_count():
    incidents = [
        Incident(key="disk-pressure:local", severity="high", title="Disk pressure", detail="95%", host="local"),
        Incident(key="disk-warning:local", severity="medium", title="Disk warning", detail="82%", host="local"),
        Incident(
            key="container-unhealthy:local:web",
            severity="high",
            title="Container unhealthy",
            detail="web unhealthy",
            host="local",
        ),
        Incident(
            key="host-unreachable:node1", severity="high", title="Host unreachable", detail="timeout", host="node1"
        ),
    ]
    skills = [
        _skill("disk", incident_keys=["disk-pressure:", "disk-warning:"], description="Disk handling"),
        _skill("container", incident_keys=["container-unhealthy:"], description="Container handling"),
        _skill("host", incident_keys=["host-unreachable:"], description="Host handling", hosts=["node1"]),
    ]
    prompt_playbooks, _ = await route_playbooks_for_incidents(
        incidents=incidents,
        playbook_skills=skills,
        thresholds=RouterThresholds(single_match_plausibility_min=0.0),
        max_selected_playbooks=2,
    )
    assert len(prompt_playbooks) == 2


@pytest.mark.asyncio
async def test_llm_budget_zero_skips_llm_calls(monkeypatch):
    incident = Incident(key="disk-pressure:local", severity="high", title="Disk pressure", detail="95% used", host="local")
    skills = [_skill("triage-disk", incident_keys=["disk-pressure:"], description="Handle disk pressure incidents")]

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("LLM helper should not be called when max_llm_calls=0")

    monkeypatch.setattr("squire.watch_playbooks.router._llm_json", _fail_if_called)
    prompt_playbooks, selections = await route_playbooks_for_incidents(
        incidents=[incident],
        playbook_skills=skills,
        llm_config=LLMConfig(model="test-model"),
        max_llm_calls=0,
        thresholds=RouterThresholds(single_match_plausibility_min=0.0),
    )

    assert selections[0].selected_playbook == "triage-disk"
    assert selections[0].path_taken == "deterministic_single"
    assert any("triage-disk" in block for block in prompt_playbooks)
