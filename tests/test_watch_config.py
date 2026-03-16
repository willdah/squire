"""Tests for WatchConfig."""

from squire.config.watch import WatchConfig


class TestWatchConfigDefaults:
    def test_default_interval(self):
        c = WatchConfig()
        assert c.interval_minutes == 5

    def test_default_risk_threshold(self):
        c = WatchConfig()
        assert c.risk_threshold == "read-only"

    def test_default_strict(self):
        c = WatchConfig()
        assert c.risk_strict is True

    def test_default_max_tool_calls(self):
        c = WatchConfig()
        assert c.max_tool_calls_per_cycle == 15

    def test_default_cycle_timeout(self):
        c = WatchConfig()
        assert c.cycle_timeout_seconds == 300

    def test_default_cycles_per_session(self):
        c = WatchConfig()
        assert c.cycles_per_session == 50

    def test_override_threshold(self):
        c = WatchConfig(risk_threshold="standard")
        assert c.risk_threshold == "standard"

    def test_override_interval(self):
        c = WatchConfig(interval_minutes=10)
        assert c.interval_minutes == 10

    def test_allow_deny_lists(self):
        c = WatchConfig(allow=["docker_ps"], deny=["run_command"])
        assert c.allow == ["docker_ps"]
        assert c.deny == ["run_command"]
