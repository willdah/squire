"""
SQLite persistence layer for Squire.

Stores system snapshots, events, and conversation messages.
Uses aiosqlite for non-blocking async SQLite access.
Connection is opened lazily on first use.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    hostname    TEXT NOT NULL,
    cpu_percent REAL,
    mem_used_mb REAL,
    mem_total_mb REAL,
    uptime      TEXT,
    raw_json    TEXT NOT NULL
)
"""

_CREATE_SNAPSHOTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp)
"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    session_id  TEXT,
    category    TEXT NOT NULL,
    tool_name   TEXT,
    summary     TEXT NOT NULL,
    details     TEXT
)
"""

_CREATE_EVENTS_INDEX_TS = """
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp)
"""

_CREATE_EVENTS_INDEX_CAT = """
CREATE INDEX IF NOT EXISTS idx_events_cat ON events(category)
"""

_CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT,
    tool_calls_json TEXT,
    tool_call_id    TEXT
)
"""

_CREATE_CONVERSATIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    last_active TEXT NOT NULL,
    preview     TEXT
)
"""


class DatabaseService:
    """Async wrapper around aiosqlite for Squire persistence.

    The connection is opened lazily on first use.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """Open and return the database connection, creating schema on first call."""
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA busy_timeout=5000")
            await self._ensure_schema()
        return self._conn

    async def _ensure_schema(self) -> None:
        """Idempotently create all tables and indexes."""
        assert self._conn is not None
        for stmt in (
            _CREATE_SNAPSHOTS,
            _CREATE_SNAPSHOTS_INDEX,
            _CREATE_EVENTS,
            _CREATE_EVENTS_INDEX_TS,
            _CREATE_EVENTS_INDEX_CAT,
            _CREATE_CONVERSATIONS,
            _CREATE_CONVERSATIONS_INDEX,
            _CREATE_SESSIONS,
        ):
            await self._conn.execute(stmt)
        await self._conn.commit()

    # --- Snapshots ---

    async def save_snapshot(self, snapshot: dict) -> None:
        """Persist a system snapshot."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO snapshots (timestamp, hostname, cpu_percent, mem_used_mb, mem_total_mb, uptime, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                snapshot.get("hostname", "unknown"),
                snapshot.get("cpu_percent", 0),
                snapshot.get("memory_used_mb", 0),
                snapshot.get("memory_total_mb", 0),
                snapshot.get("uptime", ""),
                json.dumps(snapshot),
            ),
        )
        await conn.commit()

    async def get_snapshots(self, since: str, until: str | None = None) -> list[dict]:
        """Retrieve snapshots within a time range.

        Args:
            since: ISO 8601 timestamp for the start of the range.
            until: Optional ISO 8601 timestamp for the end. Defaults to now.
        """
        conn = await self._get_conn()
        until = until or datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "SELECT raw_json FROM snapshots WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
            (since, until),
        )
        rows = await cursor.fetchall()
        return [json.loads(row[0]) for row in rows]

    # --- Events ---

    async def log_event(
        self,
        *,
        category: str,
        summary: str,
        session_id: str | None = None,
        tool_name: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log a discrete event."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO events (timestamp, session_id, category, tool_name, summary, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, session_id, category, tool_name, summary, details),
        )
        await conn.commit()

    async def get_events(self, since: str, category: str | None = None, limit: int = 100) -> list[dict]:
        """Retrieve events since a timestamp, optionally filtered by category."""
        conn = await self._get_conn()
        if category:
            cursor = await conn.execute(
                "SELECT * FROM events WHERE timestamp >= ? AND category = ? ORDER BY timestamp DESC LIMIT ?",
                (since, category, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                (since, limit),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Conversations ---

    async def create_session(self, session_id: str, preview: str = "") -> None:
        """Register a new chat session."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, created_at, last_active, preview) VALUES (?, ?, ?, ?)",
            (session_id, now, now, preview),
        )
        await conn.commit()

    async def update_session_active(self, session_id: str) -> None:
        """Touch the last_active timestamp for a session."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_id = ?",
            (now, session_id),
        )
        await conn.commit()

    async def save_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str | None = None,
        tool_calls_json: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """Persist a single conversation message."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO conversations (session_id, timestamp, role, content, tool_calls_json, tool_call_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, now, role, content, tool_calls_json, tool_call_id),
        )
        await conn.commit()

    async def get_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        """Retrieve conversation messages for a session."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY timestamp LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent chat sessions."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
