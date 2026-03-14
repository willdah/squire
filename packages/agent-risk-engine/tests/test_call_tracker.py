"""Tests for CallTracker — Layer 3 loop/repetition detection."""

from agent_risk_engine.state_monitor import CallTracker


class TestHealthyState:
    def test_empty_history(self):
        tracker = CallTracker()
        state = tracker.check()
        assert state.healthy is True
        assert state.warnings == []
        assert state.risk_adjustment == 0

    def test_varied_calls(self):
        tracker = CallTracker()
        for name in ["read", "write", "search", "read", "list"]:
            tracker.record(name)
        state = tracker.check()
        assert state.healthy is True


class TestLoopDetection:
    def test_consecutive_repetition_triggers(self):
        tracker = CallTracker(loop_threshold=3)
        for _ in range(3):
            tracker.record("stuck_tool")
        state = tracker.check()
        assert not state.healthy
        assert any("loop" in w.lower() for w in state.warnings)
        assert state.risk_adjustment >= 2

    def test_below_threshold_no_trigger(self):
        tracker = CallTracker(loop_threshold=3)
        tracker.record("tool")
        tracker.record("tool")
        state = tracker.check()
        assert state.healthy is True

    def test_interrupted_sequence_no_trigger(self):
        tracker = CallTracker(loop_threshold=3)
        tracker.record("tool")
        tracker.record("tool")
        tracker.record("other")
        tracker.record("tool")
        state = tracker.check()
        # The last 3 are ["tool", "other", "tool"] — not all the same
        assert state.healthy is True

    def test_custom_threshold(self):
        tracker = CallTracker(loop_threshold=5)
        for _ in range(4):
            tracker.record("tool")
        state = tracker.check()
        assert state.healthy is True

        tracker.record("tool")
        state = tracker.check()
        assert not state.healthy


class TestRepetitionRatio:
    def test_high_repetition_triggers(self):
        tracker = CallTracker(window=10, loop_threshold=100)  # disable loop detection
        # 8 out of 10 = 80% > 70%
        for _ in range(8):
            tracker.record("dominant")
        tracker.record("other1")
        tracker.record("other2")
        state = tracker.check()
        assert any("repetition" in w.lower() for w in state.warnings)

    def test_low_repetition_no_trigger(self):
        tracker = CallTracker(window=10, loop_threshold=100)
        for i in range(10):
            tracker.record(f"tool_{i % 5}")
        state = tracker.check()
        # Max 2 out of 10 = 20% — well below 70%
        assert state.healthy is True

    def test_needs_minimum_calls(self):
        tracker = CallTracker(loop_threshold=100)
        # 3 of same in 3 calls = 100%, but < 5 total calls and count <= 3
        for _ in range(3):
            tracker.record("tool")
        state = tracker.check()
        # Ratio check requires >= 5 calls and count > 3
        assert not any("repetition" in w.lower() for w in state.warnings)


class TestWindow:
    def test_old_calls_evicted(self):
        tracker = CallTracker(window=5, loop_threshold=3)
        # Fill window with "old"
        for _ in range(5):
            tracker.record("old")
        # Now push them out
        for _ in range(5):
            tracker.record("new")
        state = tracker.check()
        # "old" is fully evicted; "new" triggers loop (5 consecutive)
        assert any("loop" in w.lower() for w in state.warnings)


class TestCallCount:
    def test_count(self):
        tracker = CallTracker()
        assert tracker.call_count == 0
        tracker.record("a")
        tracker.record("b")
        assert tracker.call_count == 2

    def test_count_respects_window(self):
        tracker = CallTracker(window=3)
        for i in range(5):
            tracker.record(f"tool_{i}")
        assert tracker.call_count == 3


class TestReset:
    def test_reset_clears_history(self):
        tracker = CallTracker()
        tracker.record("tool")
        tracker.record("tool")
        tracker.reset()
        assert tracker.call_count == 0
        assert tracker.check().healthy is True
