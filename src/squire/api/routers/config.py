"""Configuration endpoints."""

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from squire.config import AppConfig, GuardrailsConfig, LLMConfig, NotificationsConfig, WatchConfig
from squire.config.loader import get_env_overrides, get_toml_path, write_toml_section
from squire.config.notifications import WebhookConfig
from squire.notifications.webhook import WebhookDispatcher

from .. import dependencies as deps
from ..dependencies import get_app_config, get_llm_config
from ..schemas import (
    AppConfigUpdate,
    ConfigDetailResponse,
    ConfigSectionMeta,
    GuardrailsConfigUpdate,
    LLMConfigUpdate,
    NotificationsConfigUpdate,
    WatchConfigPatch,
)

router = APIRouter()

# Fields that should never be exposed via the API
_REDACTED = "••••••"


def _redact_llm(data: dict) -> dict:
    """Redact potentially sensitive LLM fields."""
    if data.get("api_base"):
        data["api_base"] = _REDACTED
    return data


def _redact_notifications(data: dict) -> dict:
    """Redact webhook URLs and auth headers."""
    for wh in data.get("webhooks", []):
        if wh.get("url"):
            wh["url"] = _REDACTED
        if wh.get("headers"):
            wh["headers"] = {k: _REDACTED for k in wh["headers"]}
    return data


# --- Section dispatch registry ---


@dataclass
class _SectionInfo:
    attr: str  # attribute name on deps module
    config_cls: type
    update_cls: type[BaseModel]
    env_prefix: str
    toml_section: str | None  # None = top-level keys
    redact: Callable | None = None


_SECTIONS: dict[str, _SectionInfo] = {
    "app": _SectionInfo("app_config", AppConfig, AppConfigUpdate, "SQUIRE_", None),
    "llm": _SectionInfo("llm_config", LLMConfig, LLMConfigUpdate, "SQUIRE_LLM_", "llm", _redact_llm),
    "watch": _SectionInfo("watch_config", WatchConfig, WatchConfigPatch, "SQUIRE_WATCH_", "watch"),
    "guardrails": _SectionInfo(
        "guardrails",
        GuardrailsConfig,
        GuardrailsConfigUpdate,
        "SQUIRE_GUARDRAILS_",
        "guardrails",
    ),
    "notifications": _SectionInfo(
        "notif_config",
        NotificationsConfig,
        NotificationsConfigUpdate,
        "SQUIRE_NOTIFICATIONS_",
        "notifications",
        _redact_notifications,
    ),
}

_IMMUTABLE_SECTIONS = {"database", "hosts", "skills"}


def _section_meta(attr: str, info: _SectionInfo) -> ConfigSectionMeta:
    """Build a ConfigSectionMeta for a config singleton."""
    cfg = getattr(deps, attr, None)
    if cfg is None:
        return ConfigSectionMeta(values={}, env_overrides=[])
    values = cfg.model_dump(mode="json")
    if info.redact:
        values = info.redact(values)
    env_overrides = get_env_overrides(info.env_prefix, type(cfg).model_fields.keys())
    return ConfigSectionMeta(values=values, env_overrides=env_overrides)


# --- GET ---


@router.get("", response_model=ConfigDetailResponse)
async def get_config(
    app_config=Depends(get_app_config),
    llm_config=Depends(get_llm_config),
):
    """Current effective configuration (all sections), with sensitive values redacted."""
    host_configs = []
    if deps.host_store is not None:
        hosts = await deps.host_store.list_hosts()
        host_configs = [h.model_dump(mode="json") for h in hosts]

    toml_path = get_toml_path()

    return ConfigDetailResponse(
        app=_section_meta("app_config", _SECTIONS["app"]),
        llm=_section_meta("llm_config", _SECTIONS["llm"]),
        database=ConfigSectionMeta(
            values=deps.db_config.model_dump(mode="json") if deps.db_config else {},
            env_overrides=(
                get_env_overrides("SQUIRE_DB_", type(deps.db_config).model_fields.keys()) if deps.db_config else []
            ),
        ),
        notifications=_section_meta("notif_config", _SECTIONS["notifications"]),
        guardrails=_section_meta("guardrails", _SECTIONS["guardrails"]),
        watch=_section_meta("watch_config", _SECTIONS["watch"]),
        hosts=host_configs,
        toml_path=str(toml_path) if toml_path else None,
    )


# --- PATCH ---


def _merge_webhooks(existing: list[WebhookConfig], incoming: list[dict]) -> list[WebhookConfig]:
    """Merge incoming webhook dicts with existing webhooks, preserving redacted fields."""
    existing_by_name = {wh.name: wh for wh in existing}
    result = []
    for wh_dict in incoming:
        name = wh_dict.get("name", "")
        old = existing_by_name.get(name)
        if old:
            # Preserve redacted URL/headers from existing webhook
            if wh_dict.get("url") == _REDACTED:
                wh_dict["url"] = old.url
            headers = wh_dict.get("headers", {})
            if headers:
                for k, v in headers.items():
                    if v == _REDACTED and k in old.headers:
                        headers[k] = old.headers[k]
                wh_dict["headers"] = headers
        result.append(WebhookConfig(**wh_dict))
    return result


@router.patch("/{section}")
async def patch_config(
    section: str,
    body: dict = Body(...),
    persist: bool = Query(False),
):
    """Update a configuration section at runtime.

    Only changed fields need to be sent. Use ``?persist=true`` to also write to squire.toml.
    """
    if section in _IMMUTABLE_SECTIONS:
        raise HTTPException(status_code=404, detail=f"Section '{section}' is not mutable at runtime")
    info = _SECTIONS.get(section)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown config section '{section}'")

    # Strip redacted sentinel values before validation (they may not parse as the target type)
    cleaned = {k: v for k, v in body.items() if v != _REDACTED}

    # Parse and validate through the update schema
    update = info.update_cls.model_validate(cleaned)
    fields = update.model_dump(exclude_none=True)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Check for env-overridden fields
    current = getattr(deps, info.attr)
    locked = get_env_overrides(info.env_prefix, fields.keys())
    if locked:
        env_vars = [f"{info.env_prefix}{f.upper()}" for f in locked]
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update env-var-overridden fields: {', '.join(env_vars)}",
        )

    # Special handling for notifications webhooks
    if section == "notifications" and "webhooks" in fields:
        fields["webhooks"] = _merge_webhooks(current.webhooks, fields["webhooks"])

    # Create new config instance with updated fields
    new_config = current.model_copy(update=fields)

    # Replace the singleton
    setattr(deps, info.attr, new_config)

    # Recreate notifier if notifications changed
    if section == "notifications" and deps.notifier is not None:
        deps.notifier = WebhookDispatcher(new_config)

    # Persist to TOML if requested
    persist_path = None
    if persist:
        # For notifications webhooks, serialize back to dicts
        persist_data = {}
        for k, v in fields.items():
            if k == "webhooks":
                persist_data[k] = [wh.model_dump() if hasattr(wh, "model_dump") else wh for wh in v]
            else:
                persist_data[k] = v
        persist_path = write_toml_section(info.toml_section, persist_data)

    values = new_config.model_dump(mode="json")
    if info.redact:
        values = info.redact(values)

    return {
        "values": values,
        "persisted": str(persist_path) if persist_path else None,
    }
