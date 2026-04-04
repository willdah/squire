"""Shared FastAPI dependencies — service singletons initialized at startup.

These are set during the app lifespan and retrieved via FastAPI's dependency
injection. Tools also receive these via the global tool registry.
"""

from squire.config import AppConfig, DatabaseConfig, GuardrailsConfig, LLMConfig, NotificationsConfig, WatchConfig
from squire.database.service import DatabaseService
from squire.hosts.store import HostStore
from squire.notifications.webhook import WebhookDispatcher
from squire.skills import SkillService
from squire.system.registry import BackendRegistry

# Singletons — populated by the lifespan context manager in app.py
db: DatabaseService | None = None
registry: BackendRegistry | None = None
notifier: WebhookDispatcher | None = None
skills_service: SkillService | None = None

# Configs — loaded once at startup
app_config: AppConfig | None = None
llm_config: LLMConfig | None = None
db_config: DatabaseConfig | None = None
notif_config: NotificationsConfig | None = None
watch_config: WatchConfig | None = None
guardrails: GuardrailsConfig | None = None
host_store: HostStore | None = None


def get_db() -> DatabaseService:
    if db is None:
        raise RuntimeError("DatabaseService not initialized")
    return db


def get_registry() -> BackendRegistry:
    if registry is None:
        raise RuntimeError("BackendRegistry not initialized")
    return registry


def get_notifier() -> WebhookDispatcher:
    if notifier is None:
        raise RuntimeError("WebhookDispatcher not initialized")
    return notifier


def get_skills_service() -> SkillService:
    if skills_service is None:
        raise RuntimeError("SkillService not initialized")
    return skills_service


def get_app_config() -> AppConfig:
    if app_config is None:
        raise RuntimeError("AppConfig not loaded")
    return app_config


def get_llm_config() -> LLMConfig:
    if llm_config is None:
        raise RuntimeError("LLMConfig not loaded")
    return llm_config


def get_watch_config() -> WatchConfig:
    if watch_config is None:
        raise RuntimeError("WatchConfig not loaded")
    return watch_config


def get_guardrails() -> GuardrailsConfig:
    if guardrails is None:
        raise RuntimeError("GuardrailsConfig not loaded")
    return guardrails


def get_host_store() -> HostStore:
    if host_store is None:
        raise RuntimeError("HostStore not initialized")
    return host_store
