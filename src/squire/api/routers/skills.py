"""Skill management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ...config import LLMConfig
from ...skills import Skill
from ...watch_autonomy import INCIDENT_FAMILY_CATALOG, Incident
from ...watch_playbooks.router import route_playbooks_for_incidents
from ..dependencies import get_llm_config, get_skills_service
from ..schemas import (
    BootstrapPlaybooksResponse,
    IncidentFamilyInfo,
    PlaybookDryRunRequest,
    PlaybookDryRunResponse,
    PlaybookDryRunSelection,
    SkillCreate,
    SkillUpdate,
)

router = APIRouter()

VALID_TRIGGERS = ("manual", "watch")
_DRY_RUN_MAX_LLM_CALLS = 8


@router.get("", response_model=list[Skill])
def list_skills(skills_service=Depends(get_skills_service)):
    """List all skills."""
    return skills_service.list_skills()


@router.get("/incident-families", response_model=list[IncidentFamilyInfo])
def list_incident_families():
    """Return canonical incident family prefixes for playbook routing."""
    return [{"prefix": prefix, "description": desc} for prefix, desc in INCIDENT_FAMILY_CATALOG.items()]


@router.post("/bootstrap-watch-playbooks", response_model=BootstrapPlaybooksResponse)
def bootstrap_watch_playbooks(skills_service=Depends(get_skills_service)):
    """Install starter watch playbooks if missing."""
    starter = [
        Skill(
            name="recover-container-unhealthy",
            description="Diagnose and recover unhealthy or restarting containers with bounded actions.",
            trigger="watch",
            hosts=["all"],
            incident_keys=["container-unhealthy:"],
            effect="write",
            instructions=(
                "When a container is unhealthy or restarting:\n"
                "1) Inspect recent logs before restart.\n"
                "2) Restart only the affected container.\n"
                "3) Do not restart the same container more than once per cycle.\n"
                "4) Verify post-restart health.\n"
                "5) Escalate if still unhealthy."
            ),
        ),
        Skill(
            name="triage-disk-pressure",
            description="Validate disk pressure signals and perform safe cleanup steps.",
            trigger="watch",
            hosts=["all"],
            incident_keys=["disk-pressure:", "disk-warning:"],
            effect="write",
            instructions=(
                "When disk pressure is detected:\n"
                "1) Verify actual primary mount utilization before remediation.\n"
                "2) Identify largest consumers with read-only diagnostics.\n"
                "3) Prefer low-risk cleanup steps first.\n"
                "4) Re-check free space after each action.\n"
                "5) Escalate with top consumers if unresolved."
            ),
        ),
    ]
    created: list[str] = []
    skipped: list[str] = []
    for skill in starter:
        if skills_service.get_skill(skill.name):
            skipped.append(skill.name)
            continue
        skills_service.save_skill(skill)
        created.append(skill.name)
    return {"created": created, "skipped": skipped}


@router.post("/playbooks/dry-run", response_model=PlaybookDryRunResponse)
async def dry_run_playbook_routing(
    body: PlaybookDryRunRequest,
    skills_service=Depends(get_skills_service),
    llm_config: LLMConfig = Depends(get_llm_config),
):
    """Simulate playbook routing for one or more incidents."""
    incidents = [
        Incident(
            key=i.key,
            severity=i.severity,
            title=i.title or i.key,
            detail=i.detail,
            host=i.host,
        )
        for i in body.incidents
    ]
    watch_skills = skills_service.list_skills(enabled_only=True, trigger="watch")
    playbook_skills = [s for s in watch_skills if s.incident_keys]
    selected_llm_config = llm_config if body.use_llm else None
    _, selections = await route_playbooks_for_incidents(
        incidents,
        playbook_skills,
        llm_config=selected_llm_config,
        max_llm_calls=_DRY_RUN_MAX_LLM_CALLS,
    )
    response_selections = [
        PlaybookDryRunSelection(
            incident={
                "key": s.incident.key,
                "severity": s.incident.severity,
                "host": s.incident.host,
                "title": s.incident.title,
                "detail": s.incident.detail,
            },
            candidate_count=s.candidate_count,
            selected_playbook=s.selected_playbook,
            path_taken=s.path_taken,
            confidence=s.confidence,
            reasoning=s.reasoning,
        )
        for s in selections
    ]
    return {"selections": response_selections}


@router.post("", response_model=Skill, status_code=201)
def create_skill(body: SkillCreate, skills_service=Depends(get_skills_service)):
    """Create a new skill."""
    if body.trigger not in VALID_TRIGGERS:
        raise HTTPException(status_code=422, detail=f"trigger must be one of {VALID_TRIGGERS}")
    if not body.instructions.strip():
        raise HTTPException(status_code=422, detail="Instructions are required")
    if not body.description.strip():
        raise HTTPException(status_code=422, detail="Description is required")
    _validate_incident_keys(body.incident_keys, allow_custom=body.allow_custom_incident_prefixes)

    if skills_service.get_skill(body.name):
        raise HTTPException(status_code=409, detail=f"A skill named '{body.name}' already exists")

    try:
        skill = Skill(
            name=body.name,
            description=body.description,
            hosts=body.hosts,
            trigger=body.trigger,
            incident_keys=body.incident_keys,
            effect=body.effect,
            instructions=body.instructions,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    skills_service.save_skill(skill)
    return skill


@router.get("/{name}", response_model=Skill)
def get_skill(name: str, skills_service=Depends(get_skills_service)):
    """Get a skill by name."""
    skill = skills_service.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"No skill named '{name}' found")
    return skill


@router.put("/{name}", response_model=Skill)
def update_skill(name: str, body: SkillUpdate, skills_service=Depends(get_skills_service)):
    """Update a skill."""
    skill = skills_service.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"No skill named '{name}' found")

    fields = body.model_dump(exclude_none=True)
    if "trigger" in fields and fields["trigger"] not in VALID_TRIGGERS:
        raise HTTPException(status_code=422, detail=f"trigger must be one of {VALID_TRIGGERS}")

    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update")
    incident_keys = fields.get("incident_keys")
    allow_custom = bool(fields.pop("allow_custom_incident_prefixes", False))
    if incident_keys is not None:
        _validate_incident_keys(incident_keys, allow_custom=allow_custom)

    updated = skill.model_copy(update=fields)
    skills_service.save_skill(updated)
    return updated


@router.delete("/{name}")
def delete_skill(name: str, skills_service=Depends(get_skills_service)):
    """Delete a skill."""
    deleted = skills_service.delete_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No skill named '{name}' found")
    return {"deleted": True}


@router.post("/{name}/toggle")
def toggle_skill(name: str, skills_service=Depends(get_skills_service)):
    """Toggle a skill's enabled state."""
    skill = skills_service.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"No skill named '{name}' found")

    updated = skill.model_copy(update={"enabled": not skill.enabled})
    skills_service.save_skill(updated)
    return {"name": name, "enabled": updated.enabled}


@router.post("/{name}/execute")
def execute_skill(name: str, skills_service=Depends(get_skills_service)):
    """Execute a skill by returning its name for the frontend to start a chat session.

    The frontend creates a normal chat session, connects via WebSocket with
    ``?skill={name}`` so the handler loads the skill into session state, and
    sends the initial message to trigger execution.
    """
    skill = skills_service.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"No skill named '{name}' found")
    if not skill.enabled:
        raise HTTPException(status_code=422, detail=f"Skill '{name}' is disabled")

    return {
        "skill_name": skill.name,
        "instructions": skill.instructions,
    }


def _validate_incident_keys(keys: list[str], *, allow_custom: bool) -> None:
    """Validate incident family prefixes against the catalog."""
    for key in keys:
        if not key.endswith(":"):
            raise HTTPException(status_code=422, detail=f"incident_keys entry must end with ':': {key}")
        if allow_custom:
            continue
        if key not in INCIDENT_FAMILY_CATALOG:
            allowed = ", ".join(sorted(INCIDENT_FAMILY_CATALOG))
            raise HTTPException(status_code=422, detail=f"Unknown incident key prefix '{key}'. Allowed: {allowed}")
