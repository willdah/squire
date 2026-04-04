"""Tests for CallTracker — standalone loop detection utility."""
import pytest

from agent_risk_engine import CallTracker


class TestHealthyState:
    def test_empty_history(self):
        tracker = CallTracker()
        ctx = tracker.check()
        assert ctx["healthy"] is True
        assert ctx["warnings"] == []

    def test_varied_calls(self):
        tracker = CallTracker()
        for name in ["a", "b", "c", "d"]:
            tracker.record(name)
        ctx = tracker.check()
        assert ctx["healthy"] is True


class TestLoopDetection:
    def test_consecutive_repetition_triggers(self):
        tracker = CallTracker()
        for _ in range(3):
            tracker.record("x")
        ctx = tracker.check()
        assert ctx["healthy"] is False
        assert any("loop" in w.lower() for w in ctx["warnings"])

    def test_below_threshold_no_trigger(self):
        tracker = CallTracker()
        tracker.record("x")
        tracker.record("x")
        ctx = tracker.check()
        assert ctx["healthy"] is True

    def test_interrupted_sequence_no_trigger(self):
        tracker = CallTracker()
        tracker.record("x")
        tracker.record("x")
        tracker.record("y")
        tracker.record("x")
        tracker.record("x")
        ctx = tracker.check()
        assert ctx["healthy"] is True or "loop" not in str(ctx["warnings"]).lower()

    def test_custom_threshold(self):
        tracker = CallTracker(loop_threshold=5)
        for _ in range(4):
            tracker.record("x")
        ctx = tracker.check()
        assert ctx["healthy"] is True
        tracker.record("x")
        ctx = tracker.check()
        assert ctx["healthy"] is False


class TestRepetitionRatio:
    def test_high_repetition_triggers(self):
        tracker = CallTracker()
        for _ in range(8):
            tracker.record("x")
        tracker.record("y")
        ctx = tracker.check()
        assert any("repetition" in w.lower() for w in ctx["warnings"])

    def test_low_repetition_no_trigger(self):
        tracker = CallTracker()
        for name in ["a", "b", "c", "d", "e"]:
            tracker.record(name)
        ctx = tracker.check()
        assert ctx["healthy"] is True

    def test_needs_minimum_calls(self):
        tracker = CallTracker()
        tracker.record("x")
        tracker.record("x")
        tracker.record("x")
        ctx = tracker.check()
        assert not any("repetition" in w.lower() for w in ctx["warnings"])

    def test_custom_ratio(self):
        tracker = CallTracker(repetition_ratio=0.5)
        for _ in range(4):
            tracker.record("x")
        for _ in range(3):
            tracker.record("y")
        ctx = tracker.check()
        assert any("repetition" in w.lower() for w in ctx["warnings"])


class TestWindow:
    def test_old_calls_evicted(self):
        tracker = CallTracker(window=5, loop_threshold=3)
        for _ in range(3):
            tracker.record("x")
        for _ in range(5):
            tracker.record("y")
        ctx = tracker.check()
        assert ctx["healthy"] is False


class TestCallCount:
    def test_count(self):
        tracker = CallTracker()
        assert tracker.call_count == 0
        tracker.record("x")
        tracker.record("y")
        assert tracker.call_count == 2

    def test_count_respects_window(self):
        tracker = CallTracker(window=3)
        for _ in range(5):
            tracker.record("x")
        assert tracker.call_count == 3


class TestReset:
    def test_reset_clears_history(self):
        tracker = CallTracker()
        for _ in range(5):
            tracker.record("x")
        tracker.reset()
        assert tracker.call_count == 0
        ctx = tracker.check()
        assert ctx["healthy"] is True


class TestCheckReturnType:
    def test_returns_dict(self):
        tracker = CallTracker()
        ctx = tracker.check()
        assert isinstance(ctx, dict)
        assert "healthy" in ctx
        assert "warnings" in ctx
