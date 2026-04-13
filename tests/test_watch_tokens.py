"""Tests for watch mode token usage tracking."""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from google.genai import types

from squire.database.service import DatabaseService
from squire.watch import _accumulate_token_count, _extract_token_usage_from_event, _persist_watch_metrics


@pytest_asyncio.fixture
async def db(tmp_path):
    db = DatabaseService(tmp_path / "test.db")
    yield db
    await db.close()


def test_extract_token_usage_from_event_with_usage_metadata():
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=14,
        candidates_token_count=6,
        total_token_count=20,
    )
    event = SimpleNamespace(usage_metadata=usage)

    input_tokens, output_tokens, total_tokens = _extract_token_usage_from_event(event)

    assert input_tokens == 14
    assert output_tokens == 6
    assert total_tokens == 20


def test_accumulate_token_count_uses_latest_non_null_value():
    assert _accumulate_token_count(None, 8) == 8
    assert _accumulate_token_count(8, 12) == 12
    assert _accumulate_token_count(20, None) == 20


@pytest.mark.asyncio
async def test_persist_watch_metrics_accumulates_token_totals(db):
    await _persist_watch_metrics(
        db,
        {
            "tool_count": 1,
            "blocked_count": 0,
            "cycle_status": "ok",
            "input_tokens": 40,
            "output_tokens": 11,
            "total_tokens": 51,
        },
    )
    await _persist_watch_metrics(
        db,
        {
            "tool_count": 0,
            "blocked_count": 1,
            "cycle_status": "error",
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    )

    assert await db.get_watch_state("total_input_tokens") == "50"
    assert await db.get_watch_state("total_output_tokens") == "16"
    assert await db.get_watch_state("total_tokens") == "66"
