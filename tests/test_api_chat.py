"""Tests for chat token usage extraction and persistence guards."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from google.genai import types

from squire.api.routers.chat import (
    _accumulate_token_count,
    _extract_token_usage_from_event,
    _maybe_backfill_history_from_db,
    _run_single_turn,
    _should_persist_assistant_turn,
    _stream_response,
)


def test_extract_token_usage_from_event_with_usage_metadata():
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=31,
        candidates_token_count=19,
        total_token_count=50,
    )
    event = SimpleNamespace(usage_metadata=usage)

    input_tokens, output_tokens, total_tokens = _extract_token_usage_from_event(event)

    assert input_tokens == 31
    assert output_tokens == 19
    assert total_tokens == 50


def test_extract_token_usage_from_event_without_usage_metadata():
    event = SimpleNamespace(usage_metadata=None)

    input_tokens, output_tokens, total_tokens = _extract_token_usage_from_event(event)

    assert input_tokens is None
    assert output_tokens is None
    assert total_tokens is None


def test_accumulate_token_count_uses_latest_non_null_value():
    assert _accumulate_token_count(None, 10) == 10
    assert _accumulate_token_count(10, 5) == 5
    assert _accumulate_token_count(15, None) == 15


def test_should_persist_assistant_turn_for_visible_content():
    assert _should_persist_assistant_turn("hello", None, None, None) is True


def test_should_persist_assistant_turn_for_token_only_usage():
    assert _should_persist_assistant_turn("", 12, None, None) is True
    assert _should_persist_assistant_turn("", None, 7, None) is True
    assert _should_persist_assistant_turn("", None, None, 19) is True


def test_should_not_persist_empty_turn_without_tokens():
    assert _should_persist_assistant_turn("", None, None, None) is False


@pytest.mark.asyncio
async def test_stream_response_skill_stops_after_text_only_followup():
    """Skill auto-continue must not loop when the model answers without tools."""
    websocket = AsyncMock()
    session = SimpleNamespace(id="sid")
    app_config = SimpleNamespace(user_id="uid")

    with patch("squire.api.routers.chat._run_single_turn", new_callable=AsyncMock) as m_turn:
        m_turn.side_effect = [
            ("Ran tools", True, None, None, None),
            ("Finished (text only)", False, None, None, None),
        ]
        session_state = {"latest_snapshot": {}, "available_hosts": []}
        await _stream_response(
            websocket=websocket,
            runner=SimpleNamespace(),
            session=session,
            agent=SimpleNamespace(name="Squire"),
            user_text="run skill",
            app_config=app_config,
            db=None,
            notifier=None,
            session_state=session_state,
            skill_active=True,
            stop_requested=None,
        )
    assert m_turn.call_count == 2
    assert m_turn.call_args_list[0].kwargs.get("state_delta") is session_state
    assert m_turn.call_args_list[1].kwargs.get("state_delta") is session_state


@pytest.mark.asyncio
async def test_stream_response_skill_stops_on_marker_after_tool_turn():
    """[SKILL COMPLETE] on a later text-only turn ends the loop (not gated on tools that turn)."""
    websocket = AsyncMock()
    session = SimpleNamespace(id="sid")
    app_config = SimpleNamespace(user_id="uid")

    with patch("squire.api.routers.chat._run_single_turn", new_callable=AsyncMock) as m_turn:
        m_turn.side_effect = [
            ("Step done", True, None, None, None),
            ("All done\n[SKILL COMPLETE]", False, None, None, None),
        ]
        await _stream_response(
            websocket=websocket,
            runner=SimpleNamespace(),
            session=session,
            agent=SimpleNamespace(name="Squire"),
            user_text="run skill",
            app_config=app_config,
            db=None,
            notifier=None,
            session_state={},
            skill_active=True,
            stop_requested=None,
        )
    assert m_turn.call_count == 2


class _FakeRunner:
    def __init__(self, events):
        self._events = events

    async def run_async(self, **kwargs):
        for event in self._events:
            yield event


def _text_event(text: str, *, partial: bool, final: bool):
    part = SimpleNamespace(
        thought=False,
        function_call=None,
        function_response=None,
        text=text,
    )
    return SimpleNamespace(
        usage_metadata=None,
        partial=partial,
        content=SimpleNamespace(parts=[part]),
        is_final_response=lambda: final,
    )


@pytest.mark.asyncio
async def test_run_single_turn_forwards_state_delta_to_runner():
    """Durable ADK session must receive state (e.g. active_skill) via run_async state_delta."""
    captured: dict = {}

    async def fake_run_async(**kwargs):
        captured.update(kwargs)
        if False:
            yield None  # pragma: no cover

    runner = SimpleNamespace(run_async=fake_run_async)
    websocket = AsyncMock()
    session = SimpleNamespace(id="sid")
    app_config = SimpleNamespace(user_id="uid")
    delta = {"active_skill": {"skill_name": "t", "hosts": ["all"], "instructions": "go"}}

    await _run_single_turn(
        websocket=websocket,
        runner=runner,
        session=session,
        agent=SimpleNamespace(name="Squire"),
        user_text="hi",
        app_config=app_config,
        db=None,
        state_delta=delta,
    )
    assert captured.get("state_delta") is delta
    assert captured.get("session_id") == "sid"
    assert captured.get("user_id") == "uid"


def test_run_single_turn_honors_stop_requested():
    stop_requested = asyncio.Event()
    stop_requested.set()
    runner = _FakeRunner([_text_event("hello", partial=True, final=False)])
    websocket = AsyncMock()
    session = SimpleNamespace(id="sid")
    app_config = SimpleNamespace(user_id="uid")

    response, tools_called, *_ = asyncio.run(
        _run_single_turn(
            websocket=websocket,
            runner=runner,
            session=session,
            agent=SimpleNamespace(name="Squire"),
            user_text="hi",
            app_config=app_config,
            db=None,
            stop_requested=stop_requested,
        )
    )
    assert response == ""
    assert tools_called is False
    websocket.send_json.assert_not_called()


def test_backfill_replays_db_messages_when_session_has_no_events():
    class _Db:
        async def get_messages(self, session_id: str, limit: int = 100):
            return [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]

    class _SessionService:
        def __init__(self):
            self.appended = []

        async def append_event(self, session, event):
            self.appended.append(event)

    session_service = _SessionService()
    runner = SimpleNamespace(session_service=session_service)
    session = SimpleNamespace(id="sid", state={}, events=[])

    asyncio.run(
        _maybe_backfill_history_from_db(
            session=session,
            runner=runner,
            db=_Db(),
            agent_name="Squire",
        )
    )
    assert len(session_service.appended) == 2
    assert session.state.get("sql_history_backfilled_v1") is True


def test_backfill_skips_when_session_already_has_events():
    class _Db:
        async def get_messages(self, session_id: str, limit: int = 100):
            return [{"role": "user", "content": "hello"}]

    class _SessionService:
        def __init__(self):
            self.appended = []

        async def append_event(self, session, event):
            self.appended.append(event)

    session_service = _SessionService()
    runner = SimpleNamespace(session_service=session_service)
    session = SimpleNamespace(id="sid", state={}, events=[object()])

    asyncio.run(
        _maybe_backfill_history_from_db(
            session=session,
            runner=runner,
            db=_Db(),
            agent_name="Squire",
        )
    )
    assert session_service.appended == []
    assert session.state.get("sql_history_backfilled_v1") is True
