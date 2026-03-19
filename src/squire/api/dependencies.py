"""Shared FastAPI dependencies — service singletons initialized at startup.

These are set during the app lifespan and retrieved via FastAPI's dependency
injection. Tools also receive these via the global tool registry.
"""

from squire.config import AppConfig, DatabaseConfig, LLMConfig, NotificationsConfig, RiskOverridesConfig, WatchConfig
from squire.config.hosts import HostConfig
from squire.database.service import DatabaseService
from squire.notifications.webhook import WebhookDispatcher
from squire.system.registry import BackendRegistry

# Singletons — populated by the lifespan context manager in app.py
db: DatabaseService | None = None
registry: BackendRegistry | None = None
notifier: WebhookDispatcher | None = None

# Configs — loaded once at startup
app_config: AppConfig | None = None
llm_config: LLMConfig | None = None
db_config: DatabaseConfig | None = None
notif_config: NotificationsConfig | None = None
watch_config: WatchConfig | None = None
risk_overrides: RiskOverridesConfig | None = None
host_configs: list[HostConfig] = []


def get_db() -> DatabaseService:
    assert db is not None, "DatabaseService not initialized"
    return db


def get_registry() -> BackendRegistry:
    assert registry is not None, "BackendRegistry not initialized"
    return registry


def get_notifier() -> WebhookDispatcher:
    assert notifier is not None, "WebhookDispatcher not initialized"
    return notifier


def get_app_config() -> AppConfig:
    assert app_config is not None, "AppConfig not loaded"
    return app_config


def get_llm_config() -> LLMConfig:
    assert llm_config is not None, "LLMConfig not loaded"
    return llm_config
