"""Phase 2 tests — incident lifecycle, skill autonomy metadata."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from squire.skills.service import Skill, SkillService

# --- Incident lifecycle --------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_incident_creates_new_row(db):
    await db.upsert_incident(
        incident_key="inc-1",
        severity="high",
        host="local",
        title="container failure",
        first_seen=datetime.now(UTC).isoformat(),
        last_seen=datetime.now(UTC).isoformat(),
        last_outcome_json={"resolved": False},
    )
    row = await db.get_incident("inc-1")
    assert row is not None
    assert row["status"] == "active"
    assert row["severity"] == "high"


@pytest.mark.asyncio
async def test_upsert_incident_preserves_manual_resolved_unless_reobserved(db):
    now = datetime.now(UTC).isoformat()
    await db.upsert_incident(
        incident_key="inc-2",
        severity="high",
        host="local",
        title="x",
        first_seen=now,
        last_seen=now,
        last_outcome_json={},
    )
    await db.resolve_incident("inc-2")
    row = await db.get_incident("inc-2")
    assert row["status"] == "resolved"

    # New observation that still reports resolved — should stay resolved.
    await db.upsert_incident(
        incident_key="inc-2",
        severity="high",
        host="local",
        title="x",
        first_seen=now,
        last_seen=datetime.now(UTC).isoformat(),
        last_outcome_json={"resolved": True},
        observed_status="resolved",
    )
    row = await db.get_incident("inc-2")
    assert row["status"] == "resolved"

    # New observation that reports active — re-opens.
    await db.upsert_incident(
        incident_key="inc-2",
        severity="high",
        host="local",
        title="x",
        first_seen=now,
        last_seen=datetime.now(UTC).isoformat(),
        last_outcome_json={},
        observed_status="active",
    )
    row = await db.get_incident("inc-2")
    assert row["status"] == "active"


@pytest.mark.asyncio
async def test_snooze_sets_until_and_expires(db):
    now_iso = datetime.now(UTC).isoformat()
    await db.upsert_incident(
        incident_key="inc-3",
        severity="low",
        host="local",
        title="x",
        first_seen=now_iso,
        last_seen=now_iso,
        last_outcome_json={},
    )
    await db.snooze_incident("inc-3", duration_seconds=3600)
    assert await db.is_incident_snoozed("inc-3") is True

    # Force expiry by editing the row.
    conn = await db._get_conn()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await conn.execute("UPDATE incidents SET snoozed_until = ? WHERE incident_key = ?", (past, "inc-3"))
    await conn.commit()
    assert await db.is_incident_snoozed("inc-3") is False


@pytest.mark.asyncio
async def test_ack_then_resolve_sets_fields(db):
    now_iso = datetime.now(UTC).isoformat()
    await db.upsert_incident(
        incident_key="inc-4",
        severity="medium",
        host="local",
        title="x",
        first_seen=now_iso,
        last_seen=now_iso,
        last_outcome_json={},
    )
    assert await db.ack_incident("inc-4") is True
    row = await db.get_incident("inc-4")
    assert row["acknowledged_at"] is not None
    assert row["status"] == "acknowledged"

    assert await db.resolve_incident("inc-4") is True
    row = await db.get_incident("inc-4")
    assert row["status"] == "resolved"
    assert row["resolved_at"] is not None


@pytest.mark.asyncio
async def test_lifecycle_methods_return_false_for_unknown_key(db):
    assert await db.ack_incident("missing") is False
    assert await db.resolve_incident("missing") is False


# --- Skill autonomy metadata ---------------------------------------------


def _write_skill(dirpath: Path, name: str, frontmatter: str, body: str = "Do stuff.") -> None:
    skill_dir = dirpath / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}\n")


def test_skill_parses_autonomy_and_category():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(
            root,
            "safe-restart",
            "name: safe-restart\n"
            "description: restart containers safely\n"
            "metadata:\n"
            "  trigger: watch\n"
            "  autonomy: propose\n"
            "  allowed_tools: [docker_container, run_command]\n"
            "  category: reliability\n",
        )
        svc = SkillService(root)
        skill = svc.get_skill("safe-restart")
        assert skill.autonomy == "propose"
        assert skill.allowed_tools == ["docker_container", "run_command"]
        assert skill.category == "reliability"


def test_skill_defaults_when_autonomy_absent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "basic", "name: basic\ndescription: foo\n")
        svc = SkillService(root)
        skill = svc.get_skill("basic")
        assert skill.autonomy == "propose"
        assert skill.allowed_tools == []
        assert skill.category is None


def test_skill_roundtrips_autonomy_fields():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = SkillService(root)
        skill = Skill(
            name="trip",
            description="roundtrip",
            autonomy="remediate",
            allowed_tools=["service_control"],
            category="maintenance",
            instructions="body",
        )
        svc.save_skill(skill)
        reloaded = svc.get_skill("trip")
        assert reloaded.autonomy == "remediate"
        assert reloaded.allowed_tools == ["service_control"]
        assert reloaded.category == "maintenance"
