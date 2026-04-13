"""Shared token usage helpers for ADK event streams."""

from typing import Any


def extract_token_usage_from_event(event: Any) -> tuple[int | None, int | None, int | None]:
    """Extract provider-reported token usage from an ADK event."""
    usage = getattr(event, "usage_metadata", None)
    if not usage:
        return None, None, None
    return (
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        getattr(usage, "total_token_count", None),
    )


def coalesce_token_count(current: int | None, event_value: int | None) -> int | None:
    """Keep the latest non-null usage value from the stream."""
    if event_value is None:
        return current
    return event_value
