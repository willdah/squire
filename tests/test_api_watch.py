"""Tests for watch mode REST API endpoints."""

import json

import pytest
import pytest_asyncio

from squire.database.service import DatabaseService


@pytest_asyncio.fixture
async def db(tmp_path):
    db = DatabaseService(tmp_path / "test.db")
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_watch_status(db):
    from squire.api.routers.watch import watch_status

    await db.set_watch_state("status", "running")
    await db.set_watch_state("cycle", "5")
    await db.set_watch_state("total_input_tokens", "120")
    await db.set_watch_state("total_output_tokens", "75")
    await db.set_watch_state("total_tokens", "195")
    result = await watch_status(db=db)
    assert result.status == "running"
    assert result.cycle == "5"
    assert result.total_input_tokens == "120"
    assert result.total_output_tokens == "75"
    assert result.total_tokens == "195"


@pytest.mark.asyncio
async def test_watch_stop(db):
    from squire.api.routers.watch import watch_stop

    result = await watch_stop(db=db)
    assert result.status == "ok"

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 1
    assert pending[0]["command"] == "stop"


@pytest.mark.asyncio
async def test_watch_stop_stale_process_finalizes_watch_artifacts(db, monkeypatch):
    from squire.api.routers.watch import watch_stop

    def _missing_process(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("squire.api.routers.watch.os.kill", _missing_process)

    await db.create_watch_run("watch_stale_stop")
    await db.create_watch_session("wss_stale_stop", watch_id="watch_stale_stop", adk_session_id="adk_stale_stop")
    await db.set_watch_state("status", "running")
    await db.set_watch_state("pid", "999999")
    await db.set_watch_state("watch_id", "watch_stale_stop")
    await db.set_watch_state("watch_session_id", "wss_stale_stop")

    result = await watch_stop(db=db)
    assert result.status == "ok"

    run = await db.get_watch_run("watch_stale_stop")
    assert run is not None
    assert run["status"] == "stopped"
    assert run["stopped_at"]

    watch_report = await db.get_watch_completion_report("watch_stale_stop")
    assert watch_report is not None
    assert watch_report["report_type"] == "watch"

    sessions = await db.list_watch_sessions_for_run("watch_stale_stop", page=1, per_page=20)
    assert len(sessions) == 1
    assert sessions[0]["status"] == "stopped"
    assert sessions[0]["session_report_id"] is not None


@pytest.mark.asyncio
async def test_watch_status_stale_process_finalizes_watch_artifacts(db, monkeypatch):
    from squire.api.routers.watch import watch_status

    def _missing_process(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("squire.api.routers.watch.os.kill", _missing_process)

    await db.create_watch_run("watch_stale_status")
    await db.create_watch_session("wss_stale_status", watch_id="watch_stale_status", adk_session_id="adk_stale_status")
    await db.set_watch_state("status", "running")
    await db.set_watch_state("pid", "999999")
    await db.set_watch_state("watch_id", "watch_stale_status")
    await db.set_watch_state("watch_session_id", "wss_stale_status")

    result = await watch_status(db=db)
    assert result.status == "stopped"

    run = await db.get_watch_run("watch_stale_status")
    assert run is not None
    assert run["status"] == "stopped"

    watch_report = await db.get_watch_completion_report("watch_stale_status")
    assert watch_report is not None
    assert watch_report["report_type"] == "watch"

    sessions = await db.list_watch_sessions_for_run("watch_stale_status", page=1, per_page=20)
    assert len(sessions) == 1
    assert sessions[0]["status"] == "stopped"
    assert sessions[0]["session_report_id"] is not None


@pytest.mark.asyncio
async def test_watch_config_update(db):
    from squire.api.routers.watch import watch_config_update
    from squire.api.schemas import WatchConfigUpdate

    update = WatchConfigUpdate(interval_minutes=1, checkin_prompt="Custom prompt")
    result = await watch_config_update(update=update, db=db)
    assert result.status == "ok"

    pending = await db.get_pending_watch_commands()
    assert len(pending) == 1
    payload = json.loads(pending[0]["payload"])
    assert payload["interval_minutes"] == 1
    assert payload["checkin_prompt"] == "Custom prompt"


@pytest.mark.asyncio
async def test_watch_cycles(db):
    from squire.api.routers.watch import watch_cycles

    await db.insert_watch_event(1, "cycle_start", json.dumps({"session_id": "s1"}))
    await db.insert_watch_event(
        1,
        "cycle_end",
        json.dumps(
            {
                "status": "ok",
                "duration_seconds": 5,
                "tool_count": 2,
                "input_tokens": 50,
                "output_tokens": 20,
                "total_tokens": 70,
            }
        ),
    )

    result = await watch_cycles(page=1, per_page=10, db=db)
    assert len(result) == 1
    assert result[0]["cycle"] == 1
    assert result[0]["input_tokens"] == 50
    assert result[0]["output_tokens"] == 20
    assert result[0]["total_tokens"] == 70


@pytest.mark.asyncio
async def test_watch_cycle_detail(db):
    from squire.api.routers.watch import watch_cycle_detail

    await db.insert_watch_event(1, "cycle_start", "{}")
    await db.insert_watch_event(1, "token", "hello")
    await db.insert_watch_event(1, "cycle_end", "{}")

    result = await watch_cycle_detail(cycle_id="1", watch_id=None, db=db)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_watch_approve(db):
    from squire.api.routers.watch import watch_approve
    from squire.api.schemas import WatchApprovalAction

    await db.insert_watch_approval(request_id="req-1", tool_name="test", args="{}", risk_level=3)

    result = await watch_approve(request_id="req-1", action=WatchApprovalAction(approved=True), db=db)
    assert result.status == "ok"

    approval = await db.get_watch_approval("req-1")
    assert approval["status"] == "approved"


@pytest.mark.asyncio
async def test_watch_approve_already_resolved(db):
    from fastapi import HTTPException

    from squire.api.routers.watch import watch_approve
    from squire.api.schemas import WatchApprovalAction

    await db.insert_watch_approval(request_id="req-1", tool_name="test", args="{}", risk_level=3)
    await db.update_watch_approval("req-1", "approved")

    with pytest.raises(HTTPException) as exc_info:
        await watch_approve(request_id="req-1", action=WatchApprovalAction(approved=True), db=db)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_watch_delete_cycles(db):
    from squire.api.routers.watch import watch_delete_cycles

    await db.insert_watch_event(1, "cycle_start", "{}")
    await db.insert_watch_event(1, "cycle_end", "{}")

    result = await watch_delete_cycles(db=db)
    assert result.status == "ok"
    assert result.message == "Cycle history cleared"

    cycles = await db.get_watch_cycles()
    assert cycles == []


@pytest.mark.asyncio
async def test_watch_reports_and_timeline(db):
    from squire.api.routers.watch import watch_report_detail, watch_reports, watch_timeline

    await db.create_watch_run("watch_1")
    await db.create_watch_session("wss_1", watch_id="watch_1", adk_session_id="adk_1")
    await db.create_watch_cycle("cyc_1", watch_id="watch_1", watch_session_id="wss_1", cycle_number=1)
    await db.close_watch_cycle(
        "cyc_1",
        status="ok",
        duration_seconds=2.0,
        tool_count=1,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        incident_key="disk-pressure",
        outcome={"resolved": True},
    )
    await db.create_watch_report(
        "rep_1",
        watch_id="watch_1",
        watch_session_id="wss_1",
        report_type="session",
        status="ok",
        title="Session report",
        digest="All good",
        report={"executive_summary": "All good"},
    )

    reports = await watch_reports(watch_id="watch_1", watch_session_id=None, page=1, per_page=20, db=db)
    assert len(reports) == 1
    assert reports[0].report_id == "rep_1"

    detail = await watch_report_detail(report_id="rep_1", db=db)
    assert detail.title == "Session report"

    timeline = await watch_timeline(watch_id="watch_1", watch_session_id=None, page=1, per_page=20, db=db)
    assert any(item.kind == "cycle" for item in timeline)
    assert any(item.kind == "report" for item in timeline)


@pytest.mark.asyncio
async def test_watch_hierarchy_endpoints_and_report_labels(db):
    from squire.api.routers.watch import (
        watch_reports,
        watch_run_detail,
        watch_run_session_cycles,
        watch_run_sessions,
        watch_runs,
    )

    await db.create_watch_run("watch_x")
    await db.create_watch_session("wss_x1", watch_id="watch_x", adk_session_id="adk_x1")
    await db.create_watch_cycle("cyc_x1", watch_id="watch_x", watch_session_id="wss_x1", cycle_number=1)
    await db.close_watch_cycle(
        "cyc_x1",
        status="ok",
        duration_seconds=1.8,
        tool_count=2,
        blocked_count=0,
        remote_tool_count=0,
        incident_count=1,
        input_tokens=15,
        output_tokens=9,
        total_tokens=24,
        incident_key="disk-pressure",
        outcome={"resolved": True},
    )
    await db.create_watch_report(
        "rep_watch_x",
        watch_id="watch_x",
        watch_session_id=None,
        report_type="watch",
        status="ok",
        title="Watch report",
        digest="Run complete",
        report={"run_summary": "Complete"},
    )
    await db.create_watch_report(
        "rep_session_x",
        watch_id="watch_x",
        watch_session_id="wss_x1",
        report_type="session",
        status="ok",
        title="Session report",
        digest="Session complete",
        report={"executive_summary": "Complete"},
    )

    runs = await watch_runs(page=1, per_page=20, db=db)
    assert len(runs) == 1
    assert runs[0].watch_id == "watch_x"
    assert runs[0].session_count == 1
    assert runs[0].cycle_count == 1
    assert runs[0].report_count == 2
    assert runs[0].watch_report_id == "rep_watch_x"

    run_detail = await watch_run_detail(watch_id="watch_x", db=db)
    assert run_detail.watch_id == "watch_x"
    assert run_detail.report_count == 2

    sessions = await watch_run_sessions(watch_id="watch_x", page=1, per_page=20, db=db)
    assert len(sessions) == 1
    assert sessions[0].watch_session_id == "wss_x1"
    assert sessions[0].session_report_id == "rep_session_x"
    assert sessions[0].session_report_status == "ok"

    cycles = await watch_run_session_cycles(watch_id="watch_x", watch_session_id="wss_x1", page=1, per_page=20, db=db)
    assert len(cycles) == 1
    assert cycles[0].cycle_id == "cyc_x1"
    assert cycles[0].status == "ok"

    reports = await watch_reports(watch_id="watch_x", watch_session_id=None, page=1, per_page=20, db=db)
    assert {report.report_type for report in reports} == {"watch", "session"}


@pytest.mark.asyncio
async def test_watch_session_by_adk_id_lookup(db):
    from squire.api.routers.watch import watch_session_by_adk_session_id

    await db.create_watch_run("watch_lookup")
    await db.create_watch_session("wss_lookup", watch_id="watch_lookup", adk_session_id="adk_lookup")

    session = await watch_session_by_adk_session_id(adk_session_id="adk_lookup", db=db)
    assert session.watch_id == "watch_lookup"
    assert session.watch_session_id == "wss_lookup"
