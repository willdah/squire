"""Phase 4 tests — insight sweep and dashboard surfaces."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from squire.watch_autonomy import insight_sweep_from_metrics


@pytest.mark.asyncio
async def test_upsert_insight_creates_and_updates(db):
    insight_id = await db.upsert_insight(
        category="security",
        host="local",
        summary="Exposed port",
        detail="Port 22 is exposed to 0.0.0.0",
        severity="medium",
    )
    assert insight_id > 0

    # Upsert with same summary updates instead of duplicating.
    insight_id2 = await db.upsert_insight(
        category="security",
        host="local",
        summary="Exposed port",
        detail="updated detail",
        severity="high",
    )
    assert insight_id2 == insight_id

    items = await db.list_insights(category="security")
    assert len(items) == 1
    assert items[0]["detail"] == "updated detail"
    assert items[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_list_insights_filters_by_category(db):
    await db.upsert_insight(category="security", host=None, summary="s1")
    await db.upsert_insight(category="maintenance", host=None, summary="m1")

    sec = await db.list_insights(category="security")
    maint = await db.list_insights(category="maintenance")
    reliability = await db.list_insights(category="reliability")

    assert [i["summary"] for i in sec] == ["s1"]
    assert [i["summary"] for i in maint] == ["m1"]
    assert reliability == []


@pytest.mark.asyncio
async def test_insight_sweep_records_audit_break(db):
    id1 = await db.insert_watch_event(cycle=1, type="cycle_start", content="a")
    await db.insert_watch_event(cycle=1, type="tool_call", content="b")

    # Tamper so the audit chain is broken.
    conn = await db._get_conn()
    await conn.execute("DELETE FROM watch_events WHERE id = ?", (id1,))
    await conn.commit()

    created = await insight_sweep_from_metrics(db)
    assert created >= 1

    items = await db.list_insights(category="security")
    assert any("audit chain" in item["summary"].lower() for item in items)


@pytest.mark.asyncio
async def test_insight_sweep_notes_rate_limit_hits(db):
    # Seed a rate_limit event within the 24h window.
    await db.insert_watch_event(
        cycle=1,
        type="rate_limit",
        content=json.dumps({"tool_name": "run_command", "count": 31, "ceiling": 30}),
    )
    created = await insight_sweep_from_metrics(db)
    assert created >= 1

    items = await db.list_insights(category="reliability")
    assert any("ceiling" in item["summary"].lower() for item in items)


@pytest.mark.asyncio
async def test_insight_sweep_high_auto_resolve_rate(db):
    # Seed 3 resolved cycles so auto-resolve rate = 100%.
    await db.create_watch_run("w")
    await db.create_watch_session("s", watch_id="w", adk_session_id="adk")
    now = datetime.now(UTC)
    conn = await db._get_conn()
    for idx in range(3):
        cid = f"c{idx}"
        await db.create_watch_cycle(cid, watch_id="w", watch_session_id="s", cycle_number=idx + 1)
        started = (now - timedelta(minutes=5)).isoformat()
        ended = now.isoformat()
        await conn.execute(
            """
            UPDATE watch_cycles SET started_at=?, ended_at=?, incident_key=?, outcome_json=?
            WHERE cycle_id = ?
            """,
            (started, ended, f"inc-{idx}", json.dumps({"resolved": True}), cid),
        )
    await conn.commit()

    created = await insight_sweep_from_metrics(db)
    assert created >= 1

    reliability = await db.list_insights(category="reliability")

    def _matches(summary: str) -> bool:
        s = summary.lower()
        return "auto-resolved" in s or "autonomy resolved" in s

    assert any(_matches(item["summary"]) for item in reliability)
