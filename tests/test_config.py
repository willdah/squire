"""Tests for configuration classes."""

import squire.config.loader as loader_mod
from squire.config import AppConfig, DatabaseConfig, GuardrailsConfig, HostConfig, LLMConfig, NotificationsConfig
from squire.config.loader import get_list_section


class TestAppConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = AppConfig()
        assert config.app_name == "Squire"
        assert config.risk_tolerance == "cautious"
        assert config.history_limit == 50
        assert config.max_tool_rounds == 10

    def test_env_override(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        monkeypatch.setenv("SQUIRE_RISK_TOLERANCE", "full-trust")
        config = AppConfig()
        assert config.risk_tolerance == "full-trust"


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert "ollama" in config.model or config.model  # has a default
        assert config.temperature >= 0


class TestDatabaseConfig:
    def test_default_path(self):
        config = DatabaseConfig()
        assert "squire.db" in str(config.path)


class TestGuardrailsConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = GuardrailsConfig()
        assert "ping" in config.commands_allow
        assert "rm" in config.commands_block
        assert config.tools_allow == []
        assert config.tools_require_approval == []
        assert config.tools_deny == []

    def test_config_paths_empty_by_default(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = GuardrailsConfig()
        assert config.config_paths == []

    def test_per_agent_tolerances_default_none(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = GuardrailsConfig()
        assert config.monitor_tolerance is None
        assert config.container_tolerance is None
        assert config.admin_tolerance is None
        assert config.notifier_tolerance is None

    def test_watch_fields_default(self, monkeypatch):
        monkeypatch.setattr(loader_mod, "_cached", {})
        config = GuardrailsConfig()
        assert config.watch_tolerance is None
        assert config.watch_tools_allow == []
        assert config.watch_tools_deny == []


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
        self._patch_toml(monkeypatch, {"risk_tolerance": "full-trust", "history_limit": 100})
        config = AppConfig()
        assert config.risk_tolerance == "full-trust"
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

    def test_guardrails_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"guardrails": {"config_paths": ["/etc/nginx/", "/opt/stacks/"]}})
        config = GuardrailsConfig()
        assert config.config_paths == ["/etc/nginx/", "/opt/stacks/"]

    def test_guardrails_tool_overrides_from_toml(self, monkeypatch):
        self._patch_toml(
            monkeypatch,
            {
                "guardrails": {
                    "tools_allow": ["docker_logs"],
                    "tools_require_approval": ["docker_compose"],
                    "tools_deny": ["run_command"],
                    "monitor_tolerance": "standard",
                }
            },
        )
        config = GuardrailsConfig()
        assert config.tools_allow == ["docker_logs"]
        assert config.tools_require_approval == ["docker_compose"]
        assert config.tools_deny == ["run_command"]
        assert config.monitor_tolerance == "standard"

    def test_guardrails_watch_subtable_flattened(self, monkeypatch):
        """[guardrails.watch] sub-table is flattened into watch_ prefixed fields."""
        self._patch_toml(
            monkeypatch,
            {
                "guardrails": {
                    "tools_allow": ["docker_logs"],
                    "watch": {
                        "tolerance": "read-only",
                        "tools_allow": ["system_info"],
                        "tools_deny": ["run_command"],
                    },
                }
            },
        )
        config = GuardrailsConfig()
        assert config.tools_allow == ["docker_logs"]
        assert config.watch_tolerance == "read-only"
        assert config.watch_tools_allow == ["system_info"]
        assert config.watch_tools_deny == ["run_command"]

    def test_notifications_config_from_toml(self, monkeypatch):
        self._patch_toml(monkeypatch, {"notifications": {"enabled": True}})
        config = NotificationsConfig()
        assert config.enabled is True

    def test_env_overrides_toml(self, monkeypatch):
        """Env vars should take precedence over TOML values."""
        self._patch_toml(monkeypatch, {"risk_tolerance": "full-trust"})
        monkeypatch.setenv("SQUIRE_RISK_TOLERANCE", "read-only")
        config = AppConfig()
        assert config.risk_tolerance == "read-only"

    def test_unknown_toml_keys_ignored(self, monkeypatch):
        self._patch_toml(monkeypatch, {"bogus_key": "value", "llm": {"bogus_nested": 42}})
        # Should not raise
        AppConfig()
        LLMConfig()

    def test_hosts_from_toml(self, monkeypatch):
        self._patch_toml(
            monkeypatch,
            {
                "hosts": [
                    {"name": "media-server", "address": "192.168.1.10", "user": "will"},
                    {"name": "nas", "address": "192.168.1.20", "user": "root", "port": 2222},
                ]
            },
        )
        host_dicts = get_list_section("hosts")
        hosts = [HostConfig(**h) for h in host_dicts]
        assert len(hosts) == 2
        assert hosts[0].name == "media-server"
        assert hosts[0].address == "192.168.1.10"
        assert hosts[0].user == "will"
        assert hosts[0].port == 22  # default
        assert hosts[1].port == 2222

    def test_hosts_empty_when_missing(self, monkeypatch):
        self._patch_toml(monkeypatch, {})
        host_dicts = get_list_section("hosts")
        assert host_dicts == []


class TestHostConfig:
    def test_defaults(self):
        host = HostConfig(name="test", address="10.0.0.1")
        assert host.user == "root"
        assert host.port == 22
        assert host.key_file is None
        assert host.tags == []

    def test_full_config(self):
        host = HostConfig(
            name="srv",
            address="10.0.0.1",
            user="admin",
            port=2222,
            key_file="~/.ssh/id_ed25519",
            tags=["docker", "media"],
        )
        assert host.name == "srv"
        assert host.tags == ["docker", "media"]
