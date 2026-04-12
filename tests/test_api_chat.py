"""Tests for chat token usage extraction."""

from types import SimpleNamespace

from google.genai import types

from squire.api.routers.chat import _extract_token_usage_from_event


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
