"""Configuration endpoints."""

from fastapi import APIRouter

from ...config import AppConfig, DatabaseConfig, LLMConfig, NotificationsConfig, SecurityConfig, WatchConfig
from ...config.app import RiskOverridesConfig
from ...config.loader import get_list_section
from ..schemas import ConfigResponse

router = APIRouter()


@router.get("", response_model=ConfigResponse)
async def get_config():
    """Current effective configuration (all sections)."""
    app = AppConfig()
    llm = LLMConfig()
    db = DatabaseConfig()
    notif = NotificationsConfig()
    sec = SecurityConfig()
    watch = WatchConfig()
    risk = RiskOverridesConfig()
    hosts = get_list_section("hosts")

    return ConfigResponse(
        app=app.model_dump(mode="json"),
        llm=llm.model_dump(mode="json"),
        database=db.model_dump(mode="json"),
        notifications=notif.model_dump(mode="json"),
        security=sec.model_dump(mode="json"),
        watch=watch.model_dump(mode="json"),
        risk=risk.model_dump(mode="json"),
        hosts=hosts,
    )
