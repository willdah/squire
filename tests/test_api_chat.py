"""Tests for chat token usage extraction and persistence guards."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from google.genai import types

from squire.api.routers.chat import (
    _accumulate_token_count,
    _extract_token_usage_from_event,
    _run_single_turn,
    _should_persist_assistant_turn,
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
