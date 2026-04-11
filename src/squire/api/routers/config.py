"""Configuration endpoints."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from squire.config import AppConfig, GuardrailsConfig, LLMConfig, NotificationsConfig, WatchConfig
from squire.config.loader import get_env_overrides, get_toml_path, write_toml_section
from squire.config.notifications import EmailConfig, WebhookConfig
from squire.config.skills import SkillsConfig
from squire.notifications.factory import build_notification_router
from squire.skills import SkillService
from squire.tools import set_notifier as tools_set_notifier

from .. import dependencies as deps
from ..dependencies import get_app_config, get_llm_config
from ..schemas import (
    AppConfigUpdate,
    ConfigDetailResponse,
    ConfigSectionMeta,
    GuardrailsConfigUpdate,
    LLMConfigUpdate,
    NotificationsConfigUpdate,
    SkillsConfigUpdate,
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
    """Redact webhook URLs, auth headers, and email password."""
    for wh in data.get("webhooks", []):
        if wh.get("url"):
            wh["url"] = _REDACTED
        if wh.get("headers"):
            wh["headers"] = {k: _REDACTED for k in wh["headers"]}
    email = data.get("email")
    if email and isinstance(email, dict):
        if email.get("smtp_password"):
            email["smtp_password"] = _REDACTED
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
    "skills": _SectionInfo("skills_config", SkillsConfig, SkillsConfigUpdate, "SQUIRE_SKILLS_", "skills"),
}

_IMMUTABLE_SECTIONS = {"database", "hosts"}


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
        skills=_section_meta("skills_config", _SECTIONS["skills"]),
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


def _normalize_email_dict(data: dict) -> dict:
    """Map UI field names to EmailConfig (e.g. ``tls`` -> ``use_tls``)."""
    out = dict(data)
    if "tls" in out and "use_tls" not in out:
        out["use_tls"] = bool(out.pop("tls"))
    return out


def _merge_email(existing: EmailConfig | None, incoming: dict) -> EmailConfig:
    """Merge PATCH email payload with existing config; preserve redacted password."""
    inc = _normalize_email_dict(dict(incoming))
    base = existing.model_dump() if existing else {}
    for k, v in inc.items():
        if k == "smtp_password" and v == _REDACTED and existing:
            base[k] = existing.smtp_password
            continue
        base[k] = v
    return EmailConfig.model_validate(base)


def _persist_value(v):
    """JSON/TOML-friendly value for ``write_toml_section``."""
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, list) and v and hasattr(v[0], "model_dump"):
        return [x.model_dump() for x in v]
    return v


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

    # Special handling for notifications webhooks + email
    if section == "notifications" and "webhooks" in fields:
        fields["webhooks"] = _merge_webhooks(current.webhooks, fields["webhooks"])
    if section == "notifications" and "email" in cleaned:
        em = cleaned["email"]
        fields["email"] = None if em is None else _merge_email(current.email, em)

    if section == "skills" and "path" in fields:
        fields["path"] = Path(fields["path"])

    # Create new config instance with updated fields
    new_config = current.model_copy(update=fields)

    # Replace the singleton
    setattr(deps, info.attr, new_config)

    # Recreate notifier if notifications changed (webhook + email, same as lifespan)
    if section == "notifications":
        old_notifier = deps.notifier
        deps.notifier = build_notification_router(new_config)
        tools_set_notifier(deps.notifier)
        if old_notifier is not None:
            await old_notifier.close()

    if section == "skills":
        deps.skills_service = SkillService(new_config.path)

    # Persist to TOML if requested
    persist_path = None
    if persist:
        persist_data = {k: _persist_value(getattr(new_config, k)) for k in fields}
        persist_path = write_toml_section(info.toml_section, persist_data)

    values = new_config.model_dump(mode="json")
    if info.redact:
        values = info.redact(values)

    return {
        "values": values,
        "persisted": str(persist_path) if persist_path else None,
    }
