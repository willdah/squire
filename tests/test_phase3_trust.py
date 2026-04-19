"""Phase 3 trust affordances — reversible actions, preview, simulate."""

import json

import pytest

from squire.callbacks.revertible import (
    RevertibleHandler,
    RevertOutcome,
    get_revertible,
    is_revertible,
    register_revertible,
)
from squire.watch_emitter import _preview_for

# --- Reversible registry -------------------------------------------------


def test_revertible_registry_roundtrip():
    class _Handler(RevertibleHandler):
        async def capture(self, args):
            return {"before": args}

        async def revert(self, args, pre_state):
            return RevertOutcome(status="success", evidence="ok", detail={})

    register_revertible("test_tool", _Handler())
    assert is_revertible("test_tool") is True
    handler = get_revertible("test_tool")
    assert handler is not None


def test_revertible_unknown_returns_none():
    assert get_revertible("nonexistent_tool") is None
    assert is_revertible("nonexistent_tool") is False


# --- Approval preview ----------------------------------------------------


def test_preview_surfaces_command_and_effect():
    preview = _preview_for("run_command", {"command": "ls -la", "host": "local"})
    assert "command=ls -la" in preview["command"]
    assert preview["effect"] in {"read", "write", "mixed"}


def test_preview_handles_empty_args():
    preview = _preview_for("system_info", {})
    assert preview["command"] == ""
    assert "effect" in preview


# --- Reversible action persistence --------------------------------------


@pytest.mark.asyncio
async def test_record_and_retrieve_reversible_action(db):
    action_id = await db.record_reversible_action(
        cycle_id="c1",
        incident_key="inc-r1",
        tool_name="restart_container",
        args={"name": "web"},
        pre_state={"status": "running"},
    )
    assert action_id > 0

    latest = await db.get_latest_reversible_action_for_incident("inc-r1")
    assert latest is not None
    assert latest["tool_name"] == "restart_container"
    assert json.loads(latest["args_json"]) == {"name": "web"}
    assert json.loads(latest["pre_state_json"]) == {"status": "running"}


@pytest.mark.asyncio
async def test_mark_reversible_action_reverted(db):
    action_id = await db.record_reversible_action(
        cycle_id="c1",
        incident_key="inc-r2",
        tool_name="x",
        args={},
        pre_state={},
    )
    await db.mark_reversible_action_reverted(action_id, status="success")

    # Subsequent get_latest should now return None because reverted_at is set.
    latest = await db.get_latest_reversible_action_for_incident("inc-r2")
    assert latest is None
