"""Configuration endpoints."""

from fastapi import APIRouter, Depends

from ...config import SecurityConfig
from ..dependencies import get_app_config, get_llm_config
from ..schemas import ConfigResponse
from .. import dependencies as deps

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


@router.get("", response_model=ConfigResponse)
async def get_config(
    app_config=Depends(get_app_config),
    llm_config=Depends(get_llm_config),
):
    """Current effective configuration (all sections), with sensitive values redacted."""
    sec = SecurityConfig()

    return ConfigResponse(
        app=app_config.model_dump(mode="json"),
        llm=_redact_llm(llm_config.model_dump(mode="json")),
        database=deps.db_config.model_dump(mode="json") if deps.db_config else {},
        notifications=_redact_notifications(
            deps.notif_config.model_dump(mode="json") if deps.notif_config else {}
        ),
        security=sec.model_dump(mode="json"),
        watch=deps.watch_config.model_dump(mode="json") if deps.watch_config else {},
        risk=deps.risk_overrides.model_dump(mode="json") if deps.risk_overrides else {},
        hosts=[h.model_dump(mode="json") for h in deps.host_configs],
    )
