"""Configuration endpoints.

Precedence for runtime config: env vars > DB overrides > ``squire.toml`` > code
defaults. UI edits land as rows in the ``config_overrides`` table; ``squire.toml``
stays user-owned and is read-only from the app's perspective.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from squire.config import AppConfig, GuardrailsConfig, LLMConfig, NotificationsConfig, WatchConfig
from squire.config.loader import get_env_overrides, get_section, get_toml_path, get_top_level
from squire.config.notifications import EmailConfig, WebhookConfig
from squire.config.skills import SkillsConfig
from squire.notifications.factory import build_notification_router
from squire.skills import SkillService
from squire.tools import set_guardrails as tools_set_guardrails
from squire.tools import set_notifier as tools_set_notifier

from .. import dependencies as deps
from ..dependencies import get_app_config, get_llm_config
from ..schemas import (
    AppConfigUpdate,
    ConfigDetailResponse,
    ConfigSectionMeta,
    ConfigSource,
    GuardrailsConfigUpdate,
    LLMConfigUpdate,
    LLMModelsResponse,
    NotificationsConfigUpdate,
    SkillsConfigUpdate,
    WatchConfigPatch,
)

router = APIRouter()

# Fields that should never be exposed via the API
_REDACTED = "••••••"

# Sentinel section name for top-level AppConfig fields (no TOML section).
_TOP_LEVEL_SECTION = "_top_"


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
    toml_section: str | None  # None = top-level keys (AppConfig)
    db_section: str  # key used in config_overrides.section
    redact: Callable | None = None


_SECTIONS: dict[str, _SectionInfo] = {
    "app": _SectionInfo("app_config", AppConfig, AppConfigUpdate, "SQUIRE_", None, _TOP_LEVEL_SECTION),
    "llm": _SectionInfo("llm_config", LLMConfig, LLMConfigUpdate, "SQUIRE_LLM_", "llm", "llm", _redact_llm),
    "watch": _SectionInfo("watch_config", WatchConfig, WatchConfigPatch, "SQUIRE_WATCH_", "watch", "watch"),
    "guardrails": _SectionInfo(
        "guardrails",
        GuardrailsConfig,
        GuardrailsConfigUpdate,
        "SQUIRE_GUARDRAILS_",
        "guardrails",
        "guardrails",
    ),
    "notifications": _SectionInfo(
        "notif_config",
        NotificationsConfig,
        NotificationsConfigUpdate,
        "SQUIRE_NOTIFICATIONS_",
        "notifications",
        "notifications",
        _redact_notifications,
    ),
    "skills": _SectionInfo(
        "skills_config",
        SkillsConfig,
        SkillsConfigUpdate,
        "SQUIRE_SKILLS_",
        "skills",
        "skills",
    ),
}

_IMMUTABLE_SECTIONS = {"database", "hosts"}


def _jsonify(value: Any) -> Any:
    """Convert a Pydantic/Path value into a JSON-friendly representation for DB storage."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    return value


def _compute_toml_keys(info: _SectionInfo) -> set[str]:
    """Return the set of field names currently set in ``squire.toml`` for this section."""
    if info.toml_section is None:
        return set(get_top_level().keys())
    preserve = {"email"} if info.db_section == "notifications" else None
    return set(get_section(info.toml_section, preserve=preserve).keys())


async def _section_meta(info: _SectionInfo) -> ConfigSectionMeta:
    """Build a ConfigSectionMeta for a config singleton, including provenance."""
    cfg = getattr(deps, info.attr, None)
    if cfg is None:
        return ConfigSectionMeta(values={}, env_overrides=[], sources={})
    values = cfg.model_dump(mode="json")
    if info.redact:
        values = info.redact(values)

    field_names = list(type(cfg).model_fields.keys())
    env_overrides = get_env_overrides(info.env_prefix, field_names)
    db_overrides: dict[str, Any] = {}
    if deps.db is not None:
        db_overrides = await deps.db.get_config_overrides(info.db_section)
    toml_keys = _compute_toml_keys(info)

    sources: dict[str, ConfigSource] = {}
    for name in field_names:
        if name in env_overrides:
            sources[name] = "env"
        elif name in db_overrides:
            sources[name] = "db"
        elif name in toml_keys:
            sources[name] = "toml"
        else:
            sources[name] = "default"

    return ConfigSectionMeta(values=values, env_overrides=env_overrides, sources=sources)


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

    db_values: dict = {}
    db_env_overrides: list[str] = []
    if deps.db_config is not None:
        db_values = deps.db_config.model_dump(mode="json")
        db_env_overrides = get_env_overrides("SQUIRE_DB_", type(deps.db_config).model_fields.keys())

    return ConfigDetailResponse(
        app=await _section_meta(_SECTIONS["app"]),
        llm=await _section_meta(_SECTIONS["llm"]),
        database=ConfigSectionMeta(
            values=db_values,
            env_overrides=db_env_overrides,
            sources={},
        ),
        notifications=await _section_meta(_SECTIONS["notifications"]),
        guardrails=await _section_meta(_SECTIONS["guardrails"]),
        watch=await _section_meta(_SECTIONS["watch"]),
        skills=await _section_meta(_SECTIONS["skills"]),
        hosts=host_configs,
        toml_path=str(toml_path) if toml_path else None,
    )


@router.get("/llm/models", response_model=LLMModelsResponse)
async def get_llm_models(llm_config=Depends(get_llm_config)):
    """List available models for the active provider."""
    import litellm

    current_model = llm_config.model
    provider = "unknown"
    resolved_api_base = llm_config.api_base
    error: str | None = None

    try:
        _, provider, _, resolved_api_base = litellm.get_llm_provider(model=current_model, api_base=llm_config.api_base)
    except Exception:
        if "/" in current_model:
            provider = current_model.split("/", 1)[0]

    try:
        discovered = litellm.get_valid_models(
            check_provider_endpoint=True,
            custom_llm_provider=provider if provider != "unknown" else None,
            api_base=resolved_api_base,
        )
    except Exception as exc:
        discovered = []
        error = str(exc)

    provider_prefix = f"{provider}/" if provider != "unknown" else ""
    normalized: list[str] = []
    for item in discovered:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name:
            continue
        if "/" in name or not provider_prefix:
            normalized.append(name)
        else:
            normalized.append(f"{provider_prefix}{name}")

    models = sorted(set(normalized + [current_model]))
    return LLMModelsResponse(provider=provider, current_model=current_model, models=models, error=error)


# --- PATCH ---


def _merge_webhooks(existing: list[WebhookConfig], incoming: list[dict]) -> list[WebhookConfig]:
    """Merge incoming webhook dicts with existing webhooks, preserving redacted fields."""
    existing_by_name = {wh.name: wh for wh in existing}
    result = []
    for wh_dict in incoming:
        name = wh_dict.get("name", "")
        old = existing_by_name.get(name)
        if old:
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


async def _rewire_after_update(section: str, new_config: Any) -> None:
    """Re-attach downstream services that hold references to a mutated config."""
    if section == "notifications":
        old_notifier = deps.notifier
        deps.notifier = build_notification_router(new_config, db=deps.db)
        tools_set_notifier(deps.notifier)
        if old_notifier is not None:
            await old_notifier.close()
    elif section == "guardrails":
        tools_set_guardrails(new_config)
    elif section == "skills":
        deps.skills_service = SkillService(new_config.path)


def _trigger_watch_reload() -> None:
    """Signal the in-process watch controller to rebuild configs at its next cycle boundary.

    Non-blocking: sets an ``asyncio.Event`` on the live controller. If no controller
    is registered yet (e.g. very early startup), this is a no-op — the controller will
    read fresh overrides the first time it enters its run loop.
    """
    if deps.watch_controller is None:
        return
    try:
        deps.watch_controller.reload()
    except Exception:
        # A failure to signal shouldn't fail the API call; watch will pick up
        # overrides on its next natural restart.
        pass


@router.patch("/{section}", response_model=ConfigSectionMeta)
async def patch_config(section: str, body: dict = Body(...)):
    """Update a configuration section at runtime.

    Only changed fields need to be sent. Writes land in the ``config_overrides``
    DB table and override ``squire.toml`` at load time. Use ``DELETE`` to revert.
    """
    if section in _IMMUTABLE_SECTIONS:
        raise HTTPException(status_code=404, detail=f"Section '{section}' is not mutable at runtime")
    info = _SECTIONS.get(section)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown config section '{section}'")

    # Strip redacted sentinel values before validation.
    cleaned = {k: v for k, v in body.items() if v != _REDACTED}

    update = info.update_cls.model_validate(cleaned)
    fields = update.model_dump(exclude_none=True)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    current = getattr(deps, info.attr)
    locked = get_env_overrides(info.env_prefix, fields.keys())
    if locked:
        env_vars = [f"{info.env_prefix}{f.upper()}" for f in locked]
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update env-var-overridden fields: {', '.join(env_vars)}",
        )

    # Special handling for notifications webhooks + email (redaction roundtrip).
    if section == "notifications" and "webhooks" in fields:
        fields["webhooks"] = _merge_webhooks(current.webhooks, fields["webhooks"])
    if section == "notifications" and "email" in cleaned:
        em = cleaned["email"]
        fields["email"] = None if em is None else _merge_email(current.email, em)

    if section == "skills" and "path" in fields:
        fields["path"] = Path(fields["path"])

    # Persist overrides to DB (JSON-safe serialization of complex values).
    if deps.db is not None:
        jsonified = {k: _jsonify(v) for k, v in fields.items()}
        await deps.db.set_config_section_overrides(info.db_section, jsonified)

    # Replace the singleton and rewire downstream services.
    new_config = current.model_copy(update=fields)
    setattr(deps, info.attr, new_config)
    await _rewire_after_update(section, new_config)
    _trigger_watch_reload()

    return await _section_meta(info)


# --- DELETE (reset overrides) ---


@router.delete("/{section}", response_model=ConfigSectionMeta)
async def reset_section(section: str):
    """Reset all UI-driven overrides for a section back to TOML/defaults."""
    if section in _IMMUTABLE_SECTIONS:
        raise HTTPException(status_code=404, detail=f"Section '{section}' is not mutable at runtime")
    info = _SECTIONS.get(section)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown config section '{section}'")

    if deps.db is not None:
        await deps.db.clear_config_section(info.db_section)

    new_config = info.config_cls()
    setattr(deps, info.attr, new_config)
    await _rewire_after_update(section, new_config)
    _trigger_watch_reload()

    return await _section_meta(info)


@router.delete("/{section}/{field}", response_model=ConfigSectionMeta)
async def reset_field(section: str, field: str):
    """Reset a single field's UI-driven override back to TOML/defaults."""
    if section in _IMMUTABLE_SECTIONS:
        raise HTTPException(status_code=404, detail=f"Section '{section}' is not mutable at runtime")
    info = _SECTIONS.get(section)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown config section '{section}'")
    if field not in info.config_cls.model_fields:
        raise HTTPException(status_code=404, detail=f"Unknown field '{field}' in section '{section}'")

    if deps.db is not None:
        await deps.db.delete_config_override(info.db_section, field)

    new_config = info.config_cls()
    setattr(deps, info.attr, new_config)
    await _rewire_after_update(section, new_config)
    _trigger_watch_reload()

    return await _section_meta(info)
