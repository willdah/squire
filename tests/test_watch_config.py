"""Tests for WatchConfig."""

from squire.config.watch import WatchConfig


class TestWatchConfigDefaults:
    def test_default_interval(self):
        c = WatchConfig()
        assert c.interval_minutes == 5

    def test_default_max_tool_calls(self):
        c = WatchConfig()
        assert c.max_tool_calls_per_cycle == 15

    def test_default_cycle_timeout(self):
        c = WatchConfig()
        assert c.cycle_timeout_seconds == 300

    def test_default_cycles_per_session(self):
        c = WatchConfig()
        assert c.cycles_per_session == 50

    def test_override_interval(self):
        c = WatchConfig(interval_minutes=10)
        assert c.interval_minutes == 10

    def test_default_notify_flags(self):
        c = WatchConfig()
        assert c.notify_on_action is True
        assert c.notify_on_blocked is True
