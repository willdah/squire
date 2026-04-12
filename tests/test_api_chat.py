"""Tests for chat token usage extraction and persistence guards."""

from types import SimpleNamespace

from google.genai import types

from squire.api.routers.chat import (
    _accumulate_token_count,
    _extract_token_usage_from_event,
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


def test_accumulate_token_count_sums_across_events():
    assert _accumulate_token_count(None, 10) == 10
    assert _accumulate_token_count(10, 5) == 15
    assert _accumulate_token_count(15, None) == 15


def test_should_persist_assistant_turn_for_visible_content():
    assert _should_persist_assistant_turn("hello", None, None, None) is True


def test_should_persist_assistant_turn_for_token_only_usage():
    assert _should_persist_assistant_turn("", 12, None, None) is True
    assert _should_persist_assistant_turn("", None, 7, None) is True
    assert _should_persist_assistant_turn("", None, None, 19) is True


def test_should_not_persist_empty_turn_without_tokens():
    assert _should_persist_assistant_turn("", None, None, None) is False
