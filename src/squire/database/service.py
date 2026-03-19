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

_CREATE_WATCH_STATE = """
CREATE TABLE IF NOT EXISTS watch_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_CREATE_ALERT_RULES = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL UNIQUE,
    condition        TEXT NOT NULL,
    host             TEXT NOT NULL DEFAULT 'all',
    severity         TEXT NOT NULL DEFAULT 'warning',
    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
    last_fired_at    TEXT,
    enabled          INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL
)
"""

_CREATE_ALERT_RULES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled)
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
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._ensure_schema()
        return self._conn

    async def _ensure_schema(self) -> None:
        """Idempotently create all tables and indexes."""
        if self._conn is None:
            raise RuntimeError("Database connection not initialized")
        for stmt in (
            _CREATE_SNAPSHOTS,
            _CREATE_SNAPSHOTS_INDEX,
            _CREATE_EVENTS,
            _CREATE_EVENTS_INDEX_TS,
            _CREATE_EVENTS_INDEX_CAT,
            _CREATE_CONVERSATIONS,
            _CREATE_CONVERSATIONS_INDEX,
            _CREATE_SESSIONS,
            _CREATE_WATCH_STATE,
            _CREATE_ALERT_RULES,
            _CREATE_ALERT_RULES_INDEX,
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

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages. Returns True if a session was deleted."""
        conn = await self._get_conn()
        await conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        cursor = await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await conn.commit()
        return cursor.rowcount > 0

    async def delete_all_sessions(self) -> int:
        """Delete all sessions and their messages. Returns the number of sessions deleted."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM sessions")
        row = await cursor.fetchone()
        count = row[0] if row else 0
        await conn.execute("DELETE FROM conversations")
        await conn.execute("DELETE FROM sessions")
        await conn.commit()
        return count

    # --- Watch State ---

    async def set_watch_state(self, key: str, value: str) -> None:
        """Set a watch state key-value pair (upsert)."""
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO watch_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        await conn.commit()

    async def get_watch_state(self, key: str) -> str | None:
        """Get a watch state value by key."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT value FROM watch_state WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None

    async def get_all_watch_state(self) -> dict[str, str]:
        """Get all watch state key-value pairs."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT key, value FROM watch_state")
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    async def clear_watch_state(self) -> None:
        """Clear all watch state (on shutdown)."""
        conn = await self._get_conn()
        await conn.execute("DELETE FROM watch_state")
        await conn.commit()

    # --- Alert Rules ---

    async def save_alert_rule(
        self,
        *,
        name: str,
        condition: str,
        host: str = "all",
        severity: str = "warning",
        cooldown_minutes: int = 30,
    ) -> int:
        """Create a new alert rule. Returns the rule ID."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            """
            INSERT INTO alert_rules (name, condition, host, severity, cooldown_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, condition, host, severity, cooldown_minutes, now),
        )
        await conn.commit()
        return cursor.lastrowid

    async def list_alert_rules(self, enabled_only: bool = False) -> list[dict]:
        """List alert rules, optionally filtered to enabled only."""
        conn = await self._get_conn()
        if enabled_only:
            cursor = await conn.execute("SELECT * FROM alert_rules WHERE enabled = 1 ORDER BY created_at")
        else:
            cursor = await conn.execute("SELECT * FROM alert_rules ORDER BY created_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_active_alert_rules(self) -> list[dict]:
        """Get all enabled alert rules."""
        return await self.list_alert_rules(enabled_only=True)

    async def delete_alert_rule(self, name: str) -> bool:
        """Delete an alert rule by name. Returns True if a rule was deleted."""
        conn = await self._get_conn()
        cursor = await conn.execute("DELETE FROM alert_rules WHERE name = ?", (name,))
        await conn.commit()
        return cursor.rowcount > 0

    _UPDATABLE_ALERT_FIELDS = frozenset(
        {
            "condition",
            "host",
            "severity",
            "cooldown_minutes",
            "enabled",
        }
    )

    async def update_alert_rule(self, name: str, **fields) -> bool:
        """Update fields of an alert rule by name.

        Only fields in ``_UPDATABLE_ALERT_FIELDS`` are accepted.
        """
        if not fields:
            return False
        invalid = set(fields) - self._UPDATABLE_ALERT_FIELDS
        if invalid:
            raise ValueError(f"Invalid alert rule fields: {invalid}")
        conn = await self._get_conn()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [name]
        cursor = await conn.execute(
            f"UPDATE alert_rules SET {set_clause} WHERE name = ?",
            values,
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def update_alert_last_fired(self, name: str) -> None:
        """Update the last_fired_at timestamp for a rule."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            "UPDATE alert_rules SET last_fired_at = ? WHERE name = ?",
            (now, name),
        )
        await conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
