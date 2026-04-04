"""Configuration endpoints."""

from fastapi import APIRouter, Depends

from .. import dependencies as deps
from ..dependencies import get_app_config, get_llm_config
from ..schemas import ConfigResponse

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
    host_configs = []
    if deps.host_store is not None:
        hosts = await deps.host_store.list_hosts()
        host_configs = [h.model_dump(mode="json") for h in hosts]

    return ConfigResponse(
        app=app_config.model_dump(mode="json"),
        llm=_redact_llm(llm_config.model_dump(mode="json")),
        database=deps.db_config.model_dump(mode="json") if deps.db_config else {},
        notifications=_redact_notifications(deps.notif_config.model_dump(mode="json") if deps.notif_config else {}),
        guardrails=deps.guardrails.model_dump(mode="json") if deps.guardrails else {},
        watch=deps.watch_config.model_dump(mode="json") if deps.watch_config else {},
        hosts=host_configs,
    )
