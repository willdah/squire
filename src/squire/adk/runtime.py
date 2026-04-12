"""Shared ADK runtime primitives for durable sessions."""

from pathlib import Path

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService


class AdkRuntime:
    """Factory for ADK runners backed by a durable SQLite session store."""

    def __init__(self, *, app_name: str, db_path: Path | str):
        self.app_name = app_name
        self.session_db_path = self._resolve_session_db_path(db_path)
        self.session_service = SqliteSessionService(str(self.session_db_path))

    @staticmethod
    def _resolve_session_db_path(db_path: Path | str) -> Path:
        """Store ADK sessions in a dedicated DB next to Squire's app database."""
        base = Path(db_path)
        if base.suffix:
            name = f"{base.stem}.adk_sessions{base.suffix}"
        else:
            name = f"{base.name}.adk_sessions.db"
        return base.with_name(name)

    def create_runner(self, *, app: App) -> Runner:
        """Create a runner using the shared durable session service."""
        return Runner(
            app_name=self.app_name,
            app=app,
            session_service=self.session_service,
            auto_create_session=False,
        )

    async def get_or_create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        state: dict,
    ):
        """Load an existing session or create it when missing."""
        session = await self.session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if session is not None:
            return session
        return await self.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            state=state,
            session_id=session_id,
        )
