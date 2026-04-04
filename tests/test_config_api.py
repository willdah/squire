"""Tests for configuration API endpoints (GET detail + PATCH)."""

import pytest

import squire.api.dependencies as deps
import squire.config.loader as loader_mod
from squire.config import AppConfig, GuardrailsConfig, LLMConfig, NotificationsConfig, WatchConfig
from squire.config.notifications import WebhookConfig


@pytest.fixture(autouse=True)
def _empty_toml(monkeypatch):
    """Ensure tests don't read the real squire.toml."""
    monkeypatch.setattr(loader_mod, "_cached", {})


@pytest.fixture
def _setup_deps(monkeypatch):
    """Populate deps singletons with default configs."""
    monkeypatch.setattr(deps, "app_config", AppConfig())
    monkeypatch.setattr(deps, "llm_config", LLMConfig())
    monkeypatch.setattr(deps, "watch_config", WatchConfig())
    monkeypatch.setattr(deps, "guardrails", GuardrailsConfig())
    monkeypatch.setattr(deps, "notif_config", NotificationsConfig())
    monkeypatch.setattr(deps, "db_config", None)
    monkeypatch.setattr(deps, "host_store", None)
    monkeypatch.setattr(deps, "notifier", None)


# --- GET /api/config ---


@pytest.mark.usefixtures("_setup_deps")
class TestGetConfig:
    async def test_returns_env_overrides(self, monkeypatch):
        from squire.api.routers.config import get_config

        monkeypatch.setenv("SQUIRE_RISK_TOLERANCE", "full-trust")
        # Recreate config so the env var is picked up
        monkeypatch.setattr(deps, "app_config", AppConfig())

        result = await get_config(app_config=deps.app_config, llm_config=deps.llm_config)
        assert "risk_tolerance" in result.app.env_overrides

    async def test_returns_section_values(self):
        from squire.api.routers.config import get_config

        result = await get_config(app_config=deps.app_config, llm_config=deps.llm_config)
        assert result.app.values["app_name"] == "Squire"
        assert "model" in result.llm.values

    async def test_returns_toml_path(self, tmp_path, monkeypatch):
        from squire.api.routers.config import get_config

        toml_file = tmp_path / "squire.toml"
        toml_file.write_text("[llm]\nmodel = 'test'\n")
        monkeypatch.setattr(loader_mod, "_SEARCH_PATHS", [toml_file])

        result = await get_config(app_config=deps.app_config, llm_config=deps.llm_config)
        assert result.toml_path == str(toml_file)


# --- PATCH /api/config/{section} ---


@pytest.mark.usefixtures("_setup_deps")
class TestPatchConfig:
    async def test_patch_app_updates_in_memory(self):
        from squire.api.routers.config import patch_config

        result = await patch_config("app", {"risk_tolerance": "full-trust"}, persist=False)
        assert result["values"]["risk_tolerance"] == "full-trust"
        assert deps.app_config.risk_tolerance == "full-trust"

    async def test_patch_llm_updates_in_memory(self):
        from squire.api.routers.config import patch_config

        result = await patch_config("llm", {"temperature": 0.8}, persist=False)
        assert deps.llm_config.temperature == 0.8
        # api_base should be redacted in response
        assert result["values"].get("api_base") != deps.llm_config.api_base or deps.llm_config.api_base is None

    async def test_patch_watch_updates_in_memory(self):
        from squire.api.routers.config import patch_config

        await patch_config("watch", {"interval_minutes": 10, "notify_on_action": False}, persist=False)
        assert deps.watch_config.interval_minutes == 10
        assert deps.watch_config.notify_on_action is False

    async def test_patch_guardrails_updates_in_memory(self):
        from squire.api.routers.config import patch_config

        await patch_config("guardrails", {"tools_deny": ["run_command"]}, persist=False)
        assert deps.guardrails.tools_deny == ["run_command"]

    async def test_rejects_env_locked_field(self, monkeypatch):
        from fastapi import HTTPException

        from squire.api.routers.config import patch_config

        monkeypatch.setenv("SQUIRE_RISK_TOLERANCE", "read-only")
        with pytest.raises(HTTPException) as exc_info:
            await patch_config("app", {"risk_tolerance": "full-trust"}, persist=False)
        assert exc_info.value.status_code == 409
        assert "SQUIRE_RISK_TOLERANCE" in exc_info.value.detail

    async def test_strips_redacted_sentinel(self):
        from squire.api.routers.config import patch_config

        original_temp = deps.llm_config.temperature
        await patch_config("llm", {"model": "new-model", "temperature": "••••••"}, persist=False)
        assert deps.llm_config.model == "new-model"
        assert deps.llm_config.temperature == original_temp

    async def test_unknown_section_404(self):
        from fastapi import HTTPException

        from squire.api.routers.config import patch_config

        with pytest.raises(HTTPException) as exc_info:
            await patch_config("bogus", {"key": "val"}, persist=False)
        assert exc_info.value.status_code == 404

    async def test_immutable_section_404(self):
        from fastapi import HTTPException

        from squire.api.routers.config import patch_config

        with pytest.raises(HTTPException) as exc_info:
            await patch_config("database", {"path": "/tmp/db"}, persist=False)
        assert exc_info.value.status_code == 404

    async def test_empty_body_400(self):
        from fastapi import HTTPException

        from squire.api.routers.config import patch_config

        with pytest.raises(HTTPException) as exc_info:
            await patch_config("app", {}, persist=False)
        assert exc_info.value.status_code == 400

    async def test_all_redacted_body_400(self):
        from fastapi import HTTPException

        from squire.api.routers.config import patch_config

        with pytest.raises(HTTPException) as exc_info:
            await patch_config("llm", {"model": "••••••"}, persist=False)
        assert exc_info.value.status_code == 400


# --- Notifications webhook merge ---


@pytest.mark.usefixtures("_setup_deps")
class TestNotificationsWebhookMerge:
    async def test_merge_preserves_redacted_url(self, monkeypatch):
        from squire.api.routers.config import patch_config

        # Set up existing webhook
        existing = NotificationsConfig(
            enabled=True,
            webhooks=[WebhookConfig(name="discord", url="https://real-url.com", events=["*"])],
        )
        monkeypatch.setattr(deps, "notif_config", existing)

        await patch_config(
            "notifications",
            {"webhooks": [{"name": "discord", "url": "••••••", "events": ["error"]}]},
            persist=False,
        )
        assert deps.notif_config.webhooks[0].url == "https://real-url.com"
        assert deps.notif_config.webhooks[0].events == ["error"]

    async def test_merge_preserves_redacted_headers(self, monkeypatch):
        from squire.api.routers.config import patch_config

        existing = NotificationsConfig(
            enabled=True,
            webhooks=[
                WebhookConfig(name="ntfy", url="https://ntfy.sh/topic", headers={"Authorization": "Bearer secret"})
            ],
        )
        monkeypatch.setattr(deps, "notif_config", existing)

        await patch_config(
            "notifications",
            {"webhooks": [{"name": "ntfy", "url": "••••••", "headers": {"Authorization": "••••••"}}]},
            persist=False,
        )
        assert deps.notif_config.webhooks[0].headers["Authorization"] == "Bearer secret"


# --- Persist to TOML ---


@pytest.mark.usefixtures("_setup_deps")
class TestPersist:
    async def test_persist_writes_toml(self, tmp_path, monkeypatch):
        import tomlkit

        from squire.api.routers.config import patch_config

        toml_file = tmp_path / "squire.toml"
        toml_file.write_text("")
        monkeypatch.setattr(loader_mod, "_SEARCH_PATHS", [toml_file])

        result = await patch_config("llm", {"temperature": 0.9}, persist=True)
        assert result["persisted"] is not None

        with open(toml_file) as f:
            doc = tomlkit.load(f)
        assert doc["llm"]["temperature"] == 0.9

    async def test_persist_top_level(self, tmp_path, monkeypatch):
        import tomlkit

        from squire.api.routers.config import patch_config

        toml_file = tmp_path / "squire.toml"
        toml_file.write_text("")
        monkeypatch.setattr(loader_mod, "_SEARCH_PATHS", [toml_file])

        await patch_config("app", {"history_limit": 100}, persist=True)

        with open(toml_file) as f:
            doc = tomlkit.load(f)
        assert doc["history_limit"] == 100
