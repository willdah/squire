"""Tests for configuration classes."""

import squire.config.loader as loader_mod
from squire.config import AppConfig, DatabaseConfig, LLMConfig, NotificationsConfig, PathsConfig


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.app_name == "Squire"
        assert config.risk_threshold == "cautious"
        assert config.history_limit == 50
        assert config.max_tool_rounds == 10

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SQUIRE_RISK_THRESHOLD", "full-trust")
        config = AppConfig()
        assert config.risk_threshold == "full-trust"


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert "ollama" in config.model or config.model  # has a default
        assert config.temperature >= 0


class TestDatabaseConfig:
    def test_default_path(self):
        config = DatabaseConfig()
        assert "squire.db" in str(config.path)


class TestPathsConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = PathsConfig()
        assert "ping" in config.command_allowlist
        assert "rm" in config.command_denylist

    def test_config_allowlist_empty_by_default(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = PathsConfig()
        assert config.config_allowlist == []


class TestNotificationsConfig:
    def test_disabled_by_default(self):
        config = NotificationsConfig()
        assert config.enabled is False
        assert config.webhooks == []


class TestTomlLoading:
    """Test that config classes load values from squire.toml."""

    def _patch_toml(self, monkeypatch, data: dict):
        """Inject fake TOML data into the loader cache."""
        monkeypatch.setattr(loader_mod, "_cached", data)

    def test_app_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"risk_threshold": "full-trust", "history_limit": 100})
        config = AppConfig()
        assert config.risk_threshold == "full-trust"
        assert config.history_limit == 100

    def test_llm_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"llm": {"model": "anthropic/claude-sonnet-4-20250514", "temperature": 0.5}})
        config = LLMConfig()
        assert config.model == "anthropic/claude-sonnet-4-20250514"
        assert config.temperature == 0.5

    def test_db_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"db": {"snapshot_interval_minutes": 30}})
        config = DatabaseConfig()
        assert config.snapshot_interval_minutes == 30

    def test_paths_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"paths": {"config_allowlist": ["/etc/nginx/", "/opt/stacks/"]}})
        config = PathsConfig()
        assert config.config_allowlist == ["/etc/nginx/", "/opt/stacks/"]

    def test_notifications_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"notifications": {"enabled": True}})
        config = NotificationsConfig()
        assert config.enabled is True

    def test_env_overrides_toml(self, monkeypatch):
        """Env vars should take precedence over TOML values."""
        self._patch_toml(monkeypatch, {"risk_threshold": "full-trust"})
        monkeypatch.setenv("SQUIRE_RISK_THRESHOLD", "read-only")
        config = AppConfig()
        assert config.risk_threshold == "read-only"

    def test_unknown_toml_keys_ignored(self, monkeypatch):
        self._patch_toml(monkeypatch, {"bogus_key": "value", "llm": {"bogus_nested": 42}})
        # Should not raise
        AppConfig()
        LLMConfig()
