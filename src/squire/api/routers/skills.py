"""Skill management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ...skills import Skill
from ..dependencies import get_skills_service
from ..schemas import SkillCreate, SkillUpdate

router = APIRouter()

VALID_TRIGGERS = ("manual", "watch")


@router.get("", response_model=list[Skill])
def list_skills(skills_service=Depends(get_skills_service)):
    """List all skills."""
    return skills_service.list_skills()


@router.post("", response_model=Skill, status_code=201)
def create_skill(body: SkillCreate, skills_service=Depends(get_skills_service)):
    """Create a new skill."""
    if body.trigger not in VALID_TRIGGERS:
        raise HTTPException(status_code=422, detail=f"trigger must be one of {VALID_TRIGGERS}")
    if not body.instructions.strip():
        raise HTTPException(status_code=422, detail="Instructions are required")
    if not body.description.strip():
        raise HTTPException(status_code=422, detail="Description is required")

    if skills_service.get_skill(body.name):
        raise HTTPException(status_code=409, detail=f"A skill named '{body.name}' already exists")

    try:
        skill = Skill(
            name=body.name,
            description=body.description,
            host=body.host,
            trigger=body.trigger,
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
