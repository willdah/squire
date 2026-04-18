"""Shared FastAPI dependencies — service singletons initialized at startup.

These are set during the app lifespan and retrieved via FastAPI's dependency
injection. Tools also receive these via the global tool registry.
"""

from typing import TYPE_CHECKING

from squire.adk.runtime import AdkRuntime
from squire.config import AppConfig, DatabaseConfig, GuardrailsConfig, LLMConfig, NotificationsConfig, WatchConfig
from squire.config.skills import SkillsConfig
from squire.database.service import DatabaseService
from squire.hosts.store import HostStore
from squire.notifications.router import NotificationRouter
from squire.skills import SkillService
from squire.system.registry import BackendRegistry

if TYPE_CHECKING:
    from squire.watch_controller import WatchController

# Singletons — populated by the lifespan context manager in app.py
db: DatabaseService | None = None
registry: BackendRegistry | None = None
notifier: NotificationRouter | None = None
skills_service: SkillService | None = None
adk_runtime: AdkRuntime | None = None
watch_controller: "WatchController | None" = None

# Configs — loaded once at startup
app_config: AppConfig | None = None
llm_config: LLMConfig | None = None
db_config: DatabaseConfig | None = None
notif_config: NotificationsConfig | None = None
watch_config: WatchConfig | None = None
guardrails: GuardrailsConfig | None = None
skills_config: SkillsConfig | None = None
host_store: HostStore | None = None


def get_db() -> DatabaseService:
    if db is None:
        raise RuntimeError("DatabaseService not initialized")
    return db


def get_registry() -> BackendRegistry:
    if registry is None:
        raise RuntimeError("BackendRegistry not initialized")
    return registry


def get_notifier() -> NotificationRouter:
    if notifier is None:
        raise RuntimeError("NotificationRouter not initialized")
    return notifier


def get_skills_service() -> SkillService:
    if skills_service is None:
        raise RuntimeError("SkillService not initialized")
    return skills_service


def get_app_config() -> AppConfig:
    if app_config is None:
        raise RuntimeError("AppConfig not loaded")
    return app_config


def get_adk_runtime() -> AdkRuntime:
    if adk_runtime is None:
        raise RuntimeError("AdkRuntime not initialized")
    return adk_runtime


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


def get_watch_controller() -> "WatchController":
    if watch_controller is None:
        raise RuntimeError("WatchController not initialized")
    return watch_controller
