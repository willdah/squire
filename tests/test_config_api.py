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
    from squire.config.skills import SkillsConfig
    from squire.skills import SkillService

    monkeypatch.setattr(deps, "app_config", AppConfig())
    monkeypatch.setattr(deps, "llm_config", LLMConfig())
    monkeypatch.setattr(deps, "watch_config", WatchConfig())
    monkeypatch.setattr(deps, "guardrails", GuardrailsConfig())
    monkeypatch.setattr(deps, "notif_config", NotificationsConfig())
    monkeypatch.setattr(deps, "skills_config", SkillsConfig())
    monkeypatch.setattr(deps, "skills_service", SkillService(deps.skills_config.path))
    monkeypatch.setattr(deps, "db_config", None)
    monkeypatch.setattr(deps, "host_store", None)
    monkeypatch.setattr(deps, "notifier", None)


# --- GET /api/config ---


@pytest.mark.usefixtures("_setup_deps")
class TestGetConfig:
    async def test_returns_env_overrides(self, monkeypatch):
        from squire.api.routers.config import get_config

        monkeypatch.setenv("SQUIRE_GUARDRAILS_RISK_TOLERANCE", "full-trust")
        monkeypatch.setattr(deps, "guardrails", GuardrailsConfig())

        result = await get_config(app_config=deps.app_config, llm_config=deps.llm_config)
        assert "risk_tolerance" in result.guardrails.env_overrides

    async def test_returns_section_values(self):
        from squire.api.routers.config import get_config

        result = await get_config(app_config=deps.app_config, llm_config=deps.llm_config)
        assert result.app.values["app_name"] == "Squire"
        assert "model" in result.llm.values
        assert "path" in result.skills.values

    async def test_returns_toml_path(self, tmp_path, monkeypatch):
        from squire.api.routers.config import get_config

        toml_file = tmp_path / "squire.toml"
        toml_file.write_text("[llm]\nmodel = 'test'\n")
        monkeypatch.setattr(loader_mod, "_SEARCH_PATHS", [toml_file])

        result = await get_config(app_config=deps.app_config, llm_config=deps.llm_config)
        assert result.toml_path == str(toml_file)


@pytest.mark.usefixtures("_setup_deps")
class TestGetLlmModels:
    async def test_returns_provider_models(self, monkeypatch):
        from squire.api.routers.config import get_llm_models

        def _fake_get_llm_provider(model: str, api_base=None):
            return ("gpt-4o-mini", "openai", None, api_base)

        def _fake_get_valid_models(**kwargs):
            assert kwargs["custom_llm_provider"] == "openai"
            return ["gpt-4o-mini", "gpt-4.1-mini"]

        monkeypatch.setattr("litellm.get_llm_provider", _fake_get_llm_provider)
        monkeypatch.setattr("litellm.get_valid_models", _fake_get_valid_models)
        monkeypatch.setattr(deps, "llm_config", LLMConfig(model="openai/gpt-4o-mini"))

        result = await get_llm_models(llm_config=deps.llm_config)
        assert result.provider == "openai"
        assert result.current_model == "openai/gpt-4o-mini"
        assert "openai/gpt-4o-mini" in result.models
        assert "openai/gpt-4.1-mini" in result.models
        assert result.error is None

    async def test_includes_current_model_when_discovery_fails(self, monkeypatch):
        from squire.api.routers.config import get_llm_models

        def _fake_get_llm_provider(model: str, api_base=None):
            return ("llama3.2:3b", "ollama_chat", None, api_base)

        def _fake_get_valid_models(**kwargs):
            raise RuntimeError("provider unavailable")

        monkeypatch.setattr("litellm.get_llm_provider", _fake_get_llm_provider)
        monkeypatch.setattr("litellm.get_valid_models", _fake_get_valid_models)
        monkeypatch.setattr(deps, "llm_config", LLMConfig(model="ollama_chat/llama3.2:3b"))

        result = await get_llm_models(llm_config=deps.llm_config)
        assert result.provider == "ollama_chat"
        assert result.models == ["ollama_chat/llama3.2:3b"]
        assert result.error == "provider unavailable"


# --- PATCH /api/config/{section} ---


@pytest.mark.usefixtures("_setup_deps")
class TestPatchConfig:
    async def test_patch_guardrails_risk_tolerance(self):
        from squire.api.routers.config import patch_config

        result = await patch_config("guardrails", {"risk_tolerance": "full-trust"}, persist=False)
        assert result["values"]["risk_tolerance"] == "full-trust"
        assert deps.guardrails.risk_tolerance == "full-trust"

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

        monkeypatch.setenv("SQUIRE_GUARDRAILS_RISK_TOLERANCE", "read-only")
        with pytest.raises(HTTPException) as exc_info:
            await patch_config("guardrails", {"risk_tolerance": "full-trust"}, persist=False)
        assert exc_info.value.status_code == 409
        assert "SQUIRE_GUARDRAILS_RISK_TOLERANCE" in exc_info.value.detail

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

    async def test_patch_skills_updates_service(self, monkeypatch, tmp_path):
        from squire.api.routers.config import patch_config

        new_dir = tmp_path / "skills2"
        new_dir.mkdir()
        await patch_config("skills", {"path": str(new_dir)}, persist=False)
        assert deps.skills_config.path == new_dir
        assert deps.skills_service._dir == new_dir

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

    async def test_merge_preserves_redacted_email_password(self, monkeypatch):
        from squire.api.routers.config import patch_config
        from squire.config.notifications import EmailConfig

        existing = NotificationsConfig(
            enabled=True,
            email=EmailConfig(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_password="secret-pass",
                from_address="a@b.c",
                to_addresses=["u@x.y"],
            ),
        )
        monkeypatch.setattr(deps, "notif_config", existing)
        monkeypatch.setattr(deps, "notifier", None)

        await patch_config(
            "notifications",
            {
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.example.com",
                    "smtp_password": "••••••",
                    "from_address": "a@b.c",
                    "to_addresses": ["u@x.y"],
                    "tls": True,
                }
            },
            persist=False,
        )
        assert deps.notif_config.email is not None
        assert deps.notif_config.email.smtp_password == "secret-pass"
        assert deps.notif_config.email.use_tls is True


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
