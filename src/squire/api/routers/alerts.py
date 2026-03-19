"""Alert rule management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ...notifications.conditions import ConditionError, parse_condition
from ..dependencies import get_db
from ..schemas import AlertRule, AlertRuleCreate, AlertRuleUpdate

router = APIRouter()


@router.get("", response_model=list[AlertRule])
async def list_alerts(db=Depends(get_db)):
    """List all alert rules."""
    rows = await db.list_alert_rules()
    return [AlertRule(**r) for r in rows]


@router.post("", response_model=AlertRule, status_code=201)
async def create_alert(body: AlertRuleCreate, db=Depends(get_db)):
    """Create a new alert rule."""
    try:
        parse_condition(body.condition)
    except ConditionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if body.severity not in ("info", "warning", "critical"):
        raise HTTPException(status_code=422, detail="severity must be 'info', 'warning', or 'critical'")

    try:
        rule_id = await db.save_alert_rule(
            name=body.name,
            condition=body.condition,
            host=body.host,
            severity=body.severity,
            cooldown_minutes=body.cooldown_minutes,
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"A rule named '{body.name}' already exists")
        raise

    # Return the created rule
    rules = await db.list_alert_rules()
    for r in rules:
        if r.get("id") == rule_id:
            return AlertRule(**r)
    return AlertRule(id=rule_id, **body.model_dump())


@router.put("/{name}", response_model=AlertRule)
async def update_alert(name: str, body: AlertRuleUpdate, db=Depends(get_db)):
    """Update an alert rule."""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update")

    if "condition" in fields:
        try:
            parse_condition(fields["condition"])
        except ConditionError as e:
            raise HTTPException(status_code=422, detail=str(e))

    if "severity" in fields and fields["severity"] not in ("info", "warning", "critical"):
        raise HTTPException(status_code=422, detail="severity must be 'info', 'warning', or 'critical'")

    updated = await db.update_alert_rule(name, **fields)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No rule named '{name}' found")

    rules = await db.list_alert_rules()
    for r in rules:
        if r.get("name") == name:
            return AlertRule(**r)
    raise HTTPException(status_code=404, detail=f"Rule '{name}' not found after update")


@router.delete("/{name}")
async def delete_alert(name: str, db=Depends(get_db)):
    """Delete an alert rule."""
    deleted = await db.delete_alert_rule(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No rule named '{name}' found")
    return {"deleted": True}


@router.post("/{name}/toggle")
async def toggle_alert(name: str, db=Depends(get_db)):
    """Toggle an alert rule's enabled state."""
    rules = await db.list_alert_rules()
    rule = next((r for r in rules if r.get("name") == name), None)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"No rule named '{name}' found")

    new_state = 0 if rule.get("enabled") else 1
    await db.update_alert_rule(name, enabled=new_state)
    return {"name": name, "enabled": bool(new_state)}
