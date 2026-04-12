"""Tests for skills API router helpers."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from squire.api.routers.skills import (
    bootstrap_watch_playbooks,
    create_skill,
    dry_run_playbook_routing,
    list_incident_families,
    update_skill,
)
from squire.api.schemas import PlaybookDryRunRequest, SkillCreate, SkillUpdate
from squire.skills import SkillService


@pytest.fixture
def skills_service(tmp_path):
    return SkillService(tmp_path)


def test_incident_family_catalog_exposed():
    families = list_incident_families()
    prefixes = {entry["prefix"] for entry in families}
    assert "disk-pressure:" in prefixes
    assert "container-unhealthy:" in prefixes


def test_create_skill_rejects_unknown_incident_prefix(skills_service):
    with pytest.raises(HTTPException) as exc_info:
        create_skill(
            SkillCreate(
                name="bad-prefix",
                description="desc",
                trigger="watch",
                hosts=["all"],
                incident_keys=["custom-prefix:"],
                instructions="Do stuff",
            ),
            skills_service=skills_service,
        )
    assert exc_info.value.status_code == 422


def test_create_skill_accepts_custom_prefix_when_toggle_set(skills_service):
    result = create_skill(
        SkillCreate(
            name="custom-prefix",
            description="desc",
            trigger="watch",
            hosts=["all"],
            incident_keys=["custom-prefix:"],
            allow_custom_incident_prefixes=True,
            instructions="Do stuff",
        ),
        skills_service=skills_service,
    )
    assert result.incident_keys == ["custom-prefix:"]


def test_update_skill_validates_incident_prefix(skills_service):
    create_skill(
        SkillCreate(
            name="to-update",
            description="desc",
            trigger="watch",
            hosts=["all"],
            incident_keys=["disk-pressure:"],
            instructions="Do stuff",
        ),
        skills_service=skills_service,
    )
    with pytest.raises(HTTPException):
        update_skill(
            "to-update",
            SkillUpdate(incident_keys=["bad-prefix:"]),
            skills_service=skills_service,
        )


def test_bootstrap_starter_playbooks(skills_service):
    result = bootstrap_watch_playbooks(skills_service=skills_service)
    assert "recover-container-unhealthy" in result["created"] or "recover-container-unhealthy" in result["skipped"]
    assert "triage-disk-pressure" in result["created"] or "triage-disk-pressure" in result["skipped"]


@pytest.mark.asyncio
async def test_dry_run_contract_fields(skills_service, monkeypatch):
    create_skill(
        SkillCreate(
            name="triage-disk-pressure",
            description="disk",
            trigger="watch",
            hosts=["all"],
            incident_keys=["disk-pressure:"],
            instructions="Do disk triage",
        ),
        skills_service=skills_service,
    )

    async def _fake_router(*args, **kwargs):
        from squire.watch_autonomy import Incident
        from squire.watch_playbooks.router import PlaybookSelection

        incident = Incident(key="disk-pressure:local", severity="high", title="disk", detail="95%", host="local")
        selection = PlaybookSelection(
            incident=incident,
            candidate_count=1,
            selected_playbook="triage-disk-pressure",
            path_taken="deterministic_single",
            confidence=0.9,
            reasoning="deterministic match",
            instructions="Do disk triage",
        )
        return ["playbook"], [selection]

    monkeypatch.setattr("squire.api.routers.skills.route_playbooks_for_incidents", _fake_router)
    response = await dry_run_playbook_routing(
        PlaybookDryRunRequest(
            incidents=[
                {
                    "key": "disk-pressure:local",
                    "severity": "high",
                    "host": "local",
                    "title": "disk",
                    "detail": "95%",
                }
            ]
        ),
        skills_service=skills_service,
        llm_config=None,
    )
    assert len(response["selections"]) == 1
    row = response["selections"][0]
    assert row.path_taken == "deterministic_single"
    assert row.selected_playbook == "triage-disk-pressure"


def test_dry_run_request_rejects_too_many_incidents():
    with pytest.raises(ValidationError):
        PlaybookDryRunRequest(
            incidents=[
                {
                    "key": f"disk-pressure:host-{idx}",
                    "severity": "high",
                    "host": "local",
                    "title": "disk",
                    "detail": "95%",
                }
                for idx in range(26)
            ]
        )
