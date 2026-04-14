"""
SQLite persistence layer for Squire.

Stores system snapshots, events, and conversation messages.
Uses aiosqlite for non-blocking async SQLite access.
Connection is opened lazily on first use.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

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
    watch_id    TEXT,
    watch_session_id TEXT,
    cycle_id    TEXT,
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

_CREATE_EVENTS_INDEX_SESSION = """
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)
"""

_CREATE_EVENTS_INDEX_WATCH = """
CREATE INDEX IF NOT EXISTS idx_events_watch ON events(watch_id)
"""

_CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT,
    tool_calls_json TEXT,
    tool_call_id    TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    total_tokens    INTEGER
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

_CREATE_WATCH_EVENTS = """
CREATE TABLE IF NOT EXISTS watch_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle      INTEGER NOT NULL,
    cycle_id   TEXT,
    watch_id   TEXT,
    watch_session_id TEXT,
    type       TEXT NOT NULL,
    content    TEXT,
    created_at TEXT NOT NULL
)
"""

_CREATE_WATCH_EVENTS_IDX_CYCLE = """
CREATE INDEX IF NOT EXISTS idx_watch_events_cycle ON watch_events(cycle)
"""

_CREATE_WATCH_EVENTS_IDX_WATCH = """
CREATE INDEX IF NOT EXISTS idx_watch_events_watch ON watch_events(watch_id)
"""

_CREATE_WATCH_EVENTS_IDX_SESSION = """
CREATE INDEX IF NOT EXISTS idx_watch_events_session ON watch_events(watch_session_id)
"""

_CREATE_WATCH_EVENTS_IDX_CYCLE_ID = """
CREATE INDEX IF NOT EXISTS idx_watch_events_cycle_id ON watch_events(cycle_id)
"""

_CREATE_WATCH_RUNS = """
CREATE TABLE IF NOT EXISTS watch_runs (
    watch_id            TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL,
    stopped_at          TEXT,
    status              TEXT NOT NULL,
    started_by          TEXT NOT NULL DEFAULT 'user',
    watch_completion_report_id INTEGER,
    created_at          TEXT NOT NULL
)
"""

_CREATE_WATCH_SESSIONS = """
CREATE TABLE IF NOT EXISTS watch_sessions (
    watch_session_id         TEXT PRIMARY KEY,
    watch_id                 TEXT NOT NULL,
    adk_session_id           TEXT NOT NULL,
    started_at               TEXT NOT NULL,
    stopped_at               TEXT,
    status                   TEXT NOT NULL,
    cycle_count              INTEGER NOT NULL DEFAULT 0,
    session_carryforward_json TEXT,
    session_outcome_json     TEXT,
    session_report_id        INTEGER,
    created_at               TEXT NOT NULL,
    FOREIGN KEY (watch_id) REFERENCES watch_runs(watch_id) ON DELETE CASCADE
)
"""

_CREATE_WATCH_SESSIONS_IDX_WATCH = """
CREATE INDEX IF NOT EXISTS idx_watch_sessions_watch ON watch_sessions(watch_id)
"""

_CREATE_WATCH_SESSIONS_IDX_ADK = """
CREATE INDEX IF NOT EXISTS idx_watch_sessions_adk ON watch_sessions(adk_session_id)
"""

_CREATE_WATCH_CYCLES = """
CREATE TABLE IF NOT EXISTS watch_cycles (
    cycle_id               TEXT PRIMARY KEY,
    watch_id               TEXT NOT NULL,
    watch_session_id       TEXT NOT NULL,
    cycle_number           INTEGER NOT NULL,
    started_at             TEXT NOT NULL,
    ended_at               TEXT,
    status                 TEXT NOT NULL DEFAULT 'running',
    duration_seconds       REAL,
    tool_count             INTEGER NOT NULL DEFAULT 0,
    blocked_count          INTEGER NOT NULL DEFAULT 0,
    remote_tool_count      INTEGER NOT NULL DEFAULT 0,
    incident_count         INTEGER NOT NULL DEFAULT 0,
    input_tokens           INTEGER,
    output_tokens          INTEGER,
    total_tokens           INTEGER,
    incident_key           TEXT,
    outcome_json           TEXT,
    error_reason           TEXT,
    cycle_carryforward_json TEXT,
    created_at             TEXT NOT NULL,
    FOREIGN KEY (watch_id) REFERENCES watch_runs(watch_id) ON DELETE CASCADE,
    FOREIGN KEY (watch_session_id) REFERENCES watch_sessions(watch_session_id) ON DELETE CASCADE
)
"""

_CREATE_WATCH_CYCLES_IDX_WATCH = """
CREATE INDEX IF NOT EXISTS idx_watch_cycles_watch ON watch_cycles(watch_id)
"""

_CREATE_WATCH_CYCLES_IDX_SESSION = """
CREATE INDEX IF NOT EXISTS idx_watch_cycles_session ON watch_cycles(watch_session_id)
"""

_CREATE_WATCH_CYCLES_IDX_NUMBER = """
CREATE INDEX IF NOT EXISTS idx_watch_cycles_number ON watch_cycles(cycle_number)
"""

_CREATE_WATCH_REPORTS = """
CREATE TABLE IF NOT EXISTS watch_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id         TEXT NOT NULL UNIQUE,
    watch_id          TEXT NOT NULL,
    watch_session_id  TEXT,
    report_type       TEXT NOT NULL,
    status            TEXT NOT NULL,
    title             TEXT NOT NULL,
    digest            TEXT NOT NULL,
    report_json       TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (watch_id) REFERENCES watch_runs(watch_id) ON DELETE CASCADE,
    FOREIGN KEY (watch_session_id) REFERENCES watch_sessions(watch_session_id) ON DELETE CASCADE
)
"""

_CREATE_WATCH_REPORTS_IDX_WATCH = """
CREATE INDEX IF NOT EXISTS idx_watch_reports_watch ON watch_reports(watch_id)
"""

_CREATE_WATCH_REPORTS_IDX_SESSION = """
CREATE INDEX IF NOT EXISTS idx_watch_reports_session ON watch_reports(watch_session_id)
"""

_CREATE_WATCH_COMMANDS = """
CREATE TABLE IF NOT EXISTS watch_commands (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    command    TEXT NOT NULL,
    payload    TEXT,
    status     TEXT NOT NULL DEFAULT 'pending',
    error      TEXT,
    created_at TEXT NOT NULL
)
"""

_CREATE_WATCH_APPROVALS = """
CREATE TABLE IF NOT EXISTS watch_approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   TEXT UNIQUE NOT NULL,
    tool_name    TEXT NOT NULL,
    args         TEXT,
    risk_level   INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    responded_at TEXT,
    created_at   TEXT NOT NULL
)
"""

_CREATE_MANAGED_HOSTS = """
CREATE TABLE IF NOT EXISTS managed_hosts (
    name         TEXT PRIMARY KEY,
    address      TEXT NOT NULL,
    user         TEXT NOT NULL DEFAULT 'root',
    port         INTEGER NOT NULL DEFAULT 22,
    key_file     TEXT NOT NULL,
    tags         TEXT NOT NULL DEFAULT '[]',
    services     TEXT NOT NULL DEFAULT '[]',
    service_root TEXT NOT NULL DEFAULT '/opt',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""


class DatabaseService:
    """Async wrapper around aiosqlite for Squire persistence.

    The connection is opened lazily on first use.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._conn_lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        """Open and return the database connection, creating schema on first call.

        Uses a lock to prevent concurrent coroutines from racing to
        initialize the connection and schema simultaneously.
        """
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
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
        core_statements = (
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
            _CREATE_WATCH_EVENTS,
            _CREATE_WATCH_EVENTS_IDX_CYCLE,
            _CREATE_WATCH_COMMANDS,
            _CREATE_WATCH_APPROVALS,
            _CREATE_WATCH_RUNS,
            _CREATE_WATCH_SESSIONS,
            _CREATE_WATCH_SESSIONS_IDX_WATCH,
            _CREATE_WATCH_SESSIONS_IDX_ADK,
            _CREATE_WATCH_CYCLES,
            _CREATE_WATCH_CYCLES_IDX_WATCH,
            _CREATE_WATCH_CYCLES_IDX_SESSION,
            _CREATE_WATCH_CYCLES_IDX_NUMBER,
            _CREATE_WATCH_REPORTS,
            _CREATE_WATCH_REPORTS_IDX_WATCH,
            _CREATE_WATCH_REPORTS_IDX_SESSION,
            _CREATE_MANAGED_HOSTS,
        )
        for stmt in core_statements:
            await self._conn.execute(stmt)
        await self._ensure_conversation_token_columns()
        await self._ensure_watch_event_columns()
        await self._ensure_event_context_columns()
        for stmt in (
            _CREATE_EVENTS_INDEX_SESSION,
            _CREATE_EVENTS_INDEX_WATCH,
            _CREATE_WATCH_EVENTS_IDX_WATCH,
            _CREATE_WATCH_EVENTS_IDX_SESSION,
            _CREATE_WATCH_EVENTS_IDX_CYCLE_ID,
        ):
            await self._conn.execute(stmt)
        await self._conn.commit()

    async def _ensure_conversation_token_columns(self) -> None:
        """Add conversation token columns for existing databases."""
        if self._conn is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await self._conn.execute("PRAGMA table_info(conversations)")
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}
        for column in ("input_tokens", "output_tokens", "total_tokens"):
            if column not in existing_columns:
                await self._conn.execute(f"ALTER TABLE conversations ADD COLUMN {column} INTEGER")

    async def _ensure_watch_event_columns(self) -> None:
        """Add watch event identifier columns for existing databases."""
        if self._conn is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await self._conn.execute("PRAGMA table_info(watch_events)")
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}
        for column, kind in (
            ("cycle_id", "TEXT"),
            ("watch_id", "TEXT"),
            ("watch_session_id", "TEXT"),
        ):
            if column not in existing_columns:
                await self._conn.execute(f"ALTER TABLE watch_events ADD COLUMN {column} {kind}")

    async def _ensure_event_context_columns(self) -> None:
        """Add event context columns for existing databases."""
        if self._conn is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await self._conn.execute("PRAGMA table_info(events)")
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}
        for column, kind in (
            ("watch_id", "TEXT"),
            ("watch_session_id", "TEXT"),
            ("cycle_id", "TEXT"),
        ):
            if column not in existing_columns:
                await self._conn.execute(f"ALTER TABLE events ADD COLUMN {column} {kind}")

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
        watch_id: str | None = None,
        watch_session_id: str | None = None,
        cycle_id: str | None = None,
        tool_name: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log a discrete event."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO events (
                timestamp, session_id, watch_id, watch_session_id, cycle_id, category, tool_name, summary, details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, session_id, watch_id, watch_session_id, cycle_id, category, tool_name, summary, details),
        )
        await conn.commit()

    async def get_events(
        self,
        since: str,
        *,
        category: str | None = None,
        session_id: str | None = None,
        watch_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve events since a timestamp, optionally filtered by category."""
        conn = await self._get_conn()
        clauses = ["timestamp >= ?"]
        params: list[object] = [since]
        if category:
            clauses.append("category = ?")
            params.append(category)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if watch_id:
            clauses.append("watch_id = ?")
            params.append(watch_id)
        where = " AND ".join(clauses)
        cursor = await conn.execute(
            f"SELECT * FROM events WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            [*params, limit],
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
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        """Persist a single conversation message."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO conversations (
                session_id,
                timestamp,
                role,
                content,
                tool_calls_json,
                tool_call_id,
                input_tokens,
                output_tokens,
                total_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, now, role, content, tool_calls_json, tool_call_id, input_tokens, output_tokens, total_tokens),
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

    async def list_sessions(self, limit: int = 20, watch_id: str | None = None) -> list[dict]:
        """List recent chat sessions.

        When ``watch_id`` is provided, restricts results to sessions that were
        initiated by that watch run (joined through ``watch_sessions.adk_session_id``).
        """
        conn = await self._get_conn()
        if watch_id:
            cursor = await conn.execute(
                """
                SELECT
                    s.*,
                    COALESCE(SUM(c.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(c.output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(c.total_tokens), 0) AS total_tokens
                FROM sessions s
                INNER JOIN watch_sessions ws ON ws.adk_session_id = s.session_id
                LEFT JOIN conversations c ON c.session_id = s.session_id
                WHERE ws.watch_id = ?
                GROUP BY s.session_id
                ORDER BY s.last_active DESC
                LIMIT ?
                """,
                (watch_id, limit),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT
                    s.*,
                    COALESCE(SUM(c.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(c.output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(c.total_tokens), 0) AS total_tokens
                FROM sessions s
                LEFT JOIN conversations c ON c.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.last_active DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_all_session_ids(self) -> list[str]:
        """List all chat session IDs without applying a limit."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT session_id FROM sessions")
        rows = await cursor.fetchall()
        return [str(row["session_id"]) for row in rows if row["session_id"]]

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

    # --- Watch Events ---

    async def insert_watch_event(
        self,
        cycle: int,
        type: str,
        content: str | None = None,
        *,
        watch_id: str | None = None,
        watch_session_id: str | None = None,
        cycle_id: str | None = None,
    ) -> int:
        """Insert a watch event and return its ID."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            """
            INSERT INTO watch_events (cycle, cycle_id, watch_id, watch_session_id, type, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cycle, cycle_id, watch_id, watch_session_id, type, content, now),
        )
        await conn.commit()
        return cursor.lastrowid

    async def get_watch_events_since(
        self,
        last_id: int,
        limit: int = 200,
        *,
        watch_id: str | None = None,
    ) -> list[dict]:
        """Tail watch events after a given ID."""
        conn = await self._get_conn()
        if watch_id:
            cursor = await conn.execute(
                "SELECT * FROM watch_events WHERE id > ? AND watch_id = ? ORDER BY id LIMIT ?",
                (last_id, watch_id, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM watch_events WHERE id > ? ORDER BY id LIMIT ?",
                (last_id, limit),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_watch_events_for_cycle(self, cycle: int | str, watch_id: str | None = None) -> list[dict]:
        """Get all events for a specific watch cycle."""
        conn = await self._get_conn()
        if isinstance(cycle, str):
            if watch_id:
                cursor = await conn.execute(
                    "SELECT * FROM watch_events WHERE cycle_id = ? AND watch_id = ? ORDER BY id",
                    (cycle, watch_id),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM watch_events WHERE cycle_id = ? ORDER BY id",
                    (cycle,),
                )
        elif watch_id:
            cursor = await conn.execute(
                "SELECT * FROM watch_events WHERE cycle = ? AND watch_id = ? ORDER BY id",
                (cycle, watch_id),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM watch_events WHERE cycle = ? ORDER BY id",
                (cycle,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_watch_cycles(
        self,
        page: int = 1,
        per_page: int = 20,
        *,
        watch_id: str | None = None,
        watch_session_id: str | None = None,
    ) -> list[dict]:
        """Get paginated cycles, preferring canonical watch_cycles rows."""
        conn = await self._get_conn()
        offset = (page - 1) * per_page
        clauses: list[str] = []
        values: list[object] = []
        if watch_id:
            clauses.append("watch_id = ?")
            values.append(watch_id)
        if watch_session_id:
            clauses.append("watch_session_id = ?")
            values.append(watch_session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = await conn.execute(
            f"""
            SELECT
                cycle_id,
                watch_id,
                watch_session_id,
                cycle_number,
                started_at,
                ended_at,
                status,
                duration_seconds,
                tool_count,
                blocked_count,
                input_tokens,
                output_tokens,
                total_tokens,
                incident_count,
                incident_key,
                outcome_json
            FROM watch_cycles
            {where}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            [*values, per_page, offset],
        )
        rows = await cursor.fetchall()
        cycles = []
        for row in rows:
            row_dict = dict(row)
            outcome = {}
            if row_dict.get("outcome_json"):
                try:
                    outcome = json.loads(row_dict["outcome_json"])
                except (json.JSONDecodeError, TypeError):
                    outcome = {}
            cycles.append(
                {
                    "cycle_id": row_dict["cycle_id"],
                    "watch_id": row_dict["watch_id"],
                    "watch_session_id": row_dict["watch_session_id"],
                    "cycle": row_dict["cycle_number"],
                    "started_at": row_dict["started_at"],
                    "ended_at": row_dict["ended_at"],
                    "status": row_dict.get("status", "unknown"),
                    "duration_seconds": row_dict.get("duration_seconds"),
                    "tool_count": row_dict.get("tool_count", 0),
                    "blocked_count": row_dict.get("blocked_count", 0),
                    "input_tokens": row_dict.get("input_tokens"),
                    "output_tokens": row_dict.get("output_tokens"),
                    "total_tokens": row_dict.get("total_tokens"),
                    "incident_count": row_dict.get("incident_count", 0),
                    "resolved": bool(outcome.get("resolved", False)),
                    "escalated": bool(outcome.get("escalated", False)),
                    "incident_key": row_dict.get("incident_key"),
                    "event_count": len(await self.get_watch_events_for_cycle(row_dict["cycle_id"])),
                }
            )
        if cycles:
            return cycles

        # Legacy fallback for DBs without canonical cycle rows.
        cursor = await conn.execute(
            """
            SELECT
                e.cycle,
                MIN(CASE WHEN e.type = 'cycle_start' THEN e.created_at END) AS started_at,
                MIN(CASE WHEN e.type = 'cycle_end' THEN e.created_at END) AS ended_at,
                MIN(CASE WHEN e.type = 'cycle_end' THEN e.content END) AS end_content,
                COUNT(*) AS event_count
            FROM watch_events e
            GROUP BY e.cycle
            ORDER BY e.cycle DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        )
        rows = await cursor.fetchall()
        cycles = []
        for row in rows:
            row_dict = dict(row)
            end_content = {}
            if row_dict.get("end_content"):
                try:
                    end_content = json.loads(row_dict["end_content"])
                except (json.JSONDecodeError, TypeError):
                    pass
            cycles.append(
                {
                    "cycle_id": None,
                    "watch_id": None,
                    "watch_session_id": None,
                    "cycle": row_dict["cycle"],
                    "started_at": row_dict["started_at"],
                    "ended_at": row_dict["ended_at"],
                    "status": end_content.get("status", "unknown"),
                    "duration_seconds": end_content.get("duration_seconds"),
                    "tool_count": end_content.get("tool_count", 0),
                    "blocked_count": end_content.get("blocked_count", 0),
                    "input_tokens": end_content.get("input_tokens"),
                    "output_tokens": end_content.get("output_tokens"),
                    "total_tokens": end_content.get("total_tokens"),
                    "incident_count": ((end_content.get("outcome") or {}).get("incident_count", 0)),
                    "resolved": ((end_content.get("outcome") or {}).get("resolved", False)),
                    "escalated": ((end_content.get("outcome") or {}).get("escalated", False)),
                    "incident_key": ((end_content.get("outcome") or {}).get("incident_fingerprint")),
                    "event_count": row_dict["event_count"],
                }
            )
        return cycles

    async def delete_watch_cycles(self) -> None:
        """Delete all watch history."""
        conn = await self._get_conn()
        await conn.execute("DELETE FROM watch_reports")
        await conn.execute("DELETE FROM watch_cycles")
        await conn.execute("DELETE FROM watch_sessions")
        await conn.execute("DELETE FROM watch_runs")
        await conn.execute("DELETE FROM watch_events")
        await conn.commit()

    async def create_watch_run(self, watch_id: str, *, started_by: str = "user") -> None:
        """Create a new watch run record."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO watch_runs (watch_id, started_at, status, started_by, created_at)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (watch_id, now, started_by, now),
        )
        await conn.commit()

    async def close_watch_run(
        self,
        watch_id: str,
        *,
        status: str,
        watch_completion_report_id: int | None = None,
    ) -> None:
        """Close a running watch."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            UPDATE watch_runs
            SET stopped_at = ?, status = ?, watch_completion_report_id = COALESCE(?, watch_completion_report_id)
            WHERE watch_id = ?
            """,
            (now, status, watch_completion_report_id, watch_id),
        )
        await conn.commit()

    async def finalize_stale_watch_run(
        self,
        watch_id: str,
        *,
        watch_session_id: str | None = None,
        reason: str = "Watch process exited unexpectedly before normal shutdown finalization.",
    ) -> dict[str, object]:
        """Finalize run/session/report artifacts when a watch process is already gone."""
        conn = await self._get_conn()

        if not watch_session_id:
            cursor = await conn.execute(
                """
                SELECT watch_session_id
                FROM watch_sessions
                WHERE watch_id = ? AND status = 'running'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (watch_id,),
            )
            row = await cursor.fetchone()
            watch_session_id = row["watch_session_id"] if row else None

        session_report_pk: int | None = None
        if watch_session_id:
            cursor = await conn.execute(
                "SELECT status, cycle_count FROM watch_sessions WHERE watch_session_id = ?",
                (watch_session_id,),
            )
            session_row = await cursor.fetchone()
            if session_row and session_row["status"] == "running":
                cycle_count = int(session_row["cycle_count"] or 0)
                session_outcome = {
                    "status": "error",
                    "goal_summary": reason,
                    "key_decisions": "",
                    "persistent_risks": reason,
                    "open_actions": "Review watch process health and restart if needed.",
                    "memories_to_carry_forward": "",
                    "parse_status": "ok",
                    "failure_reason": "stale_watch_process",
                }
                session_report = {
                    "executive_summary": reason,
                    "incidents_seen": f"{cycle_count} completed cycle(s) were recorded before the process exit.",
                    "actions_taken": "No additional actions executed after process exit.",
                    "blocked_or_denied_actions": "0 blocked/denied action(s).",
                    "verification_results": "Finalized from stale state cleanup.",
                    "open_risks": reason,
                    "recommended_follow_ups": "Inspect host logs and restart watch mode if needed.",
                    "cost_usage": {"total_tokens": 0, "cycle_count": cycle_count},
                    "meta": {"watch_id": watch_id, "watch_session_id": watch_session_id},
                }
                session_report_id = f"wsr_{uuid4().hex[:12]}"
                session_report_pk = await self.create_watch_report(
                    session_report_id,
                    watch_id=watch_id,
                    watch_session_id=watch_session_id,
                    report_type="session",
                    status="error",
                    title=f"Session report {watch_session_id}",
                    digest=reason,
                    report=session_report,
                )
                await self.close_watch_session(
                    watch_session_id,
                    status="stopped",
                    cycle_count=cycle_count,
                    session_carryforward=session_outcome,
                    session_outcome=session_outcome,
                    session_report_id=session_report_pk,
                )

        existing_watch_report = await self.get_watch_completion_report(watch_id)
        watch_report_pk: int | None = existing_watch_report["id"] if existing_watch_report else None
        if watch_report_pk is None:
            session_cursor = await conn.execute(
                "SELECT COUNT(*) AS count FROM watch_sessions WHERE watch_id = ?",
                (watch_id,),
            )
            session_count_row = await session_cursor.fetchone()
            session_count = int(session_count_row["count"] if session_count_row else 0)

            cycle_cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) AS cycle_count,
                    COALESCE(SUM(tool_count), 0) AS action_count,
                    COALESCE(SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END), 0) AS error_count
                FROM watch_cycles
                WHERE watch_id = ?
                """,
                (watch_id,),
            )
            cycle_count_row = await cycle_cursor.fetchone()
            cycle_count = int(cycle_count_row["cycle_count"] if cycle_count_row else 0)
            action_count = int(cycle_count_row["action_count"] if cycle_count_row else 0)
            error_count = int(cycle_count_row["error_count"] if cycle_count_row else 0)
            run_summary = f"Watch {watch_id} completed with {session_count} session(s) and {cycle_count} cycle(s)."

            watch_report_id = f"wrp_{uuid4().hex[:12]}"
            watch_report = {
                "run_summary": run_summary,
                "session_rollup": f"{session_count} session(s); {error_count} error cycle(s).",
                "major_actions": f"{action_count} actions executed.",
                "error_and_timeout_analysis": reason,
                "learning_memory_rollup": "Stale-process recovery artifact.",
                "next_watch_recommendations": "Restart watch mode and verify host health.",
                "cost_usage": {"total_tokens": 0},
            }
            watch_report_pk = await self.create_watch_report(
                watch_report_id,
                watch_id=watch_id,
                report_type="watch",
                status="error",
                title=f"Watch completion report {watch_id}",
                digest=reason,
                report=watch_report,
            )

        await self.close_watch_run(watch_id, status="stopped", watch_completion_report_id=watch_report_pk)
        return {
            "watch_id": watch_id,
            "watch_session_id": watch_session_id,
            "session_report_id": session_report_pk,
            "watch_report_id": watch_report_pk,
        }

    async def create_watch_session(self, watch_session_id: str, *, watch_id: str, adk_session_id: str) -> None:
        """Create a watch session row."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO watch_sessions (watch_session_id, watch_id, adk_session_id, started_at, status, created_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (watch_session_id, watch_id, adk_session_id, now, now),
        )
        await conn.commit()

    async def close_watch_session(
        self,
        watch_session_id: str,
        *,
        status: str,
        cycle_count: int,
        session_carryforward: dict | None = None,
        session_outcome: dict | None = None,
        session_report_id: int | None = None,
    ) -> None:
        """Close a watch session with summary artifacts."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            UPDATE watch_sessions
            SET stopped_at = ?, status = ?, cycle_count = ?, session_carryforward_json = ?, session_outcome_json = ?,
                session_report_id = COALESCE(?, session_report_id)
            WHERE watch_session_id = ?
            """,
            (
                now,
                status,
                cycle_count,
                json.dumps(session_carryforward or {}),
                json.dumps(session_outcome or {}),
                session_report_id,
                watch_session_id,
            ),
        )
        await conn.commit()

    async def create_watch_cycle(
        self,
        cycle_id: str,
        *,
        watch_id: str,
        watch_session_id: str,
        cycle_number: int,
    ) -> None:
        """Create a cycle row before execution."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO watch_cycles (cycle_id, watch_id, watch_session_id, cycle_number, started_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cycle_id, watch_id, watch_session_id, cycle_number, now, now),
        )
        await conn.commit()

    async def close_watch_cycle(
        self,
        cycle_id: str,
        *,
        status: str,
        duration_seconds: float,
        tool_count: int,
        blocked_count: int,
        remote_tool_count: int,
        incident_count: int,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
        incident_key: str | None,
        outcome: dict,
        error_reason: str | None = None,
        cycle_carryforward: dict | None = None,
    ) -> None:
        """Close a cycle row after execution."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            UPDATE watch_cycles
            SET ended_at = ?, status = ?, duration_seconds = ?, tool_count = ?, blocked_count = ?,
                remote_tool_count = ?, incident_count = ?, input_tokens = ?, output_tokens = ?, total_tokens = ?,
                incident_key = ?, outcome_json = ?, error_reason = ?, cycle_carryforward_json = ?
            WHERE cycle_id = ?
            """,
            (
                now,
                status,
                duration_seconds,
                tool_count,
                blocked_count,
                remote_tool_count,
                incident_count,
                input_tokens,
                output_tokens,
                total_tokens,
                incident_key,
                json.dumps(outcome or {}),
                error_reason,
                json.dumps(cycle_carryforward or {}),
                cycle_id,
            ),
        )
        await conn.commit()

    async def create_watch_report(
        self,
        report_id: str,
        *,
        watch_id: str,
        report_type: str,
        title: str,
        digest: str,
        report: dict,
        watch_session_id: str | None = None,
        status: str = "ok",
    ) -> int:
        """Persist a watch/session report."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            """
            INSERT INTO watch_reports (
                report_id, watch_id, watch_session_id, report_type, status, title, digest, report_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (report_id, watch_id, watch_session_id, report_type, status, title, digest, json.dumps(report), now),
        )
        await conn.commit()
        return cursor.lastrowid

    async def get_watch_report(self, report_id: str) -> dict | None:
        """Fetch a watch report by external report ID."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM watch_reports WHERE report_id = ?", (report_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_watch_reports(
        self,
        *,
        watch_id: str | None = None,
        watch_session_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict]:
        """List watch reports newest-first."""
        conn = await self._get_conn()
        offset = (page - 1) * per_page
        clauses: list[str] = []
        values: list[object] = []
        if watch_id:
            clauses.append("watch_id = ?")
            values.append(watch_id)
        if watch_session_id:
            clauses.append("watch_session_id = ?")
            values.append(watch_session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = await conn.execute(
            f"SELECT * FROM watch_reports {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*values, per_page, offset],
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_watch_session_report(self, watch_id: str, watch_session_id: str) -> dict | None:
        """Fetch a specific session report."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT * FROM watch_reports
            WHERE watch_id = ? AND watch_session_id = ? AND report_type = 'session'
            ORDER BY created_at DESC LIMIT 1
            """,
            (watch_id, watch_session_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_watch_completion_report(self, watch_id: str) -> dict | None:
        """Fetch the latest watch completion report."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT * FROM watch_reports
            WHERE watch_id = ? AND report_type = 'watch'
            ORDER BY created_at DESC LIMIT 1
            """,
            (watch_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_watch_runs(self, *, page: int = 1, per_page: int = 20) -> list[dict]:
        """List watch runs with aggregated counts."""
        conn = await self._get_conn()
        offset = (page - 1) * per_page
        cursor = await conn.execute(
            """
            SELECT
                wr.watch_id,
                wr.started_at,
                wr.stopped_at,
                wr.status,
                COUNT(DISTINCT ws.watch_session_id) AS session_count,
                COUNT(DISTINCT wc.cycle_id) AS cycle_count,
                COUNT(DISTINCT wrp.report_id) AS report_count,
                MAX(CASE WHEN wrp.report_type = 'watch' THEN wrp.report_id END) AS watch_report_id
            FROM watch_runs wr
            LEFT JOIN watch_sessions ws ON ws.watch_id = wr.watch_id
            LEFT JOIN watch_cycles wc ON wc.watch_id = wr.watch_id
            LEFT JOIN watch_reports wrp ON wrp.watch_id = wr.watch_id
            GROUP BY wr.watch_id, wr.started_at, wr.stopped_at, wr.status
            ORDER BY wr.started_at DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_watch_run(self, watch_id: str) -> dict | None:
        """Fetch one watch run summary."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT
                wr.watch_id,
                wr.started_at,
                wr.stopped_at,
                wr.status,
                COUNT(DISTINCT ws.watch_session_id) AS session_count,
                COUNT(DISTINCT wc.cycle_id) AS cycle_count,
                COUNT(DISTINCT wrp.report_id) AS report_count,
                MAX(CASE WHEN wrp.report_type = 'watch' THEN wrp.report_id END) AS watch_report_id
            FROM watch_runs wr
            LEFT JOIN watch_sessions ws ON ws.watch_id = wr.watch_id
            LEFT JOIN watch_cycles wc ON wc.watch_id = wr.watch_id
            LEFT JOIN watch_reports wrp ON wrp.watch_id = wr.watch_id
            WHERE wr.watch_id = ?
            GROUP BY wr.watch_id, wr.started_at, wr.stopped_at, wr.status
            """,
            (watch_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_watch_sessions_for_run(
        self,
        watch_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> list[dict]:
        """List sessions for a watch run with session-report metadata."""
        conn = await self._get_conn()
        offset = (page - 1) * per_page
        cursor = await conn.execute(
            """
            SELECT
                ws.watch_session_id,
                ws.watch_id,
                ws.adk_session_id,
                ws.started_at,
                ws.stopped_at,
                ws.status,
                MAX(ws.cycle_count, COALESCE(wc.live_cycle_count, 0)) AS cycle_count,
                wr.report_id AS session_report_id,
                wr.status AS session_report_status,
                wr.title AS session_report_title
            FROM watch_sessions ws
            LEFT JOIN (
                SELECT watch_session_id, COUNT(*) AS live_cycle_count
                FROM watch_cycles
                GROUP BY watch_session_id
            ) wc
              ON wc.watch_session_id = ws.watch_session_id
            LEFT JOIN watch_reports wr
              ON wr.id = (
                SELECT id
                FROM watch_reports
                WHERE watch_session_id = ws.watch_session_id
                  AND report_type = 'session'
                ORDER BY created_at DESC
                LIMIT 1
              )
            WHERE ws.watch_id = ?
            ORDER BY ws.started_at DESC
            LIMIT ? OFFSET ?
            """,
            (watch_id, per_page, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_watch_session_by_adk_session_id(self, adk_session_id: str) -> dict | None:
        """Resolve a watch session by ADK session identifier."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT
                ws.watch_session_id,
                ws.watch_id,
                ws.adk_session_id,
                ws.started_at,
                ws.stopped_at,
                ws.status,
                MAX(ws.cycle_count, COALESCE(wc.live_cycle_count, 0)) AS cycle_count,
                wr.report_id AS session_report_id,
                wr.status AS session_report_status,
                wr.title AS session_report_title
            FROM watch_sessions ws
            LEFT JOIN (
                SELECT watch_session_id, COUNT(*) AS live_cycle_count
                FROM watch_cycles
                GROUP BY watch_session_id
            ) wc
              ON wc.watch_session_id = ws.watch_session_id
            LEFT JOIN watch_reports wr
              ON wr.id = (
                SELECT id
                FROM watch_reports
                WHERE watch_session_id = ws.watch_session_id
                  AND report_type = 'session'
                ORDER BY created_at DESC
                LIMIT 1
              )
            WHERE ws.adk_session_id = ?
            ORDER BY ws.started_at DESC
            LIMIT 1
            """,
            (adk_session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_watch_cycles_for_session(
        self,
        watch_id: str,
        watch_session_id: str,
        *,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict]:
        """List cycles under a specific watch session."""
        conn = await self._get_conn()
        offset = (page - 1) * per_page
        cursor = await conn.execute(
            """
            SELECT
                cycle_id,
                watch_id,
                watch_session_id,
                cycle_number,
                started_at,
                ended_at,
                status,
                duration_seconds,
                tool_count,
                blocked_count,
                incident_count,
                input_tokens,
                output_tokens,
                total_tokens,
                incident_key
            FROM watch_cycles
            WHERE watch_id = ? AND watch_session_id = ?
            ORDER BY cycle_number DESC
            LIMIT ? OFFSET ?
            """,
            (watch_id, watch_session_id, per_page, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_watch_activity_timeline(
        self,
        *,
        watch_id: str | None = None,
        watch_session_id: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict]:
        """Return mixed cycle/report timeline cards for the workbench."""
        offset = (page - 1) * per_page
        conn = await self._get_conn()
        clauses: list[str] = []
        values: list[object] = []
        if watch_id:
            clauses.append("watch_id = ?")
            values.append(watch_id)
        if watch_session_id:
            clauses.append("watch_session_id = ?")
            values.append(watch_session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = await conn.execute(
            f"""
            SELECT
                cycle_id AS item_id,
                'cycle' AS kind,
                watch_id,
                watch_session_id,
                cycle_number AS cycle,
                started_at AS created_at,
                status,
                incident_count,
                tool_count,
                blocked_count,
                input_tokens,
                output_tokens,
                total_tokens,
                outcome_json AS payload_json
            FROM watch_cycles
            {where}
            UNION ALL
            SELECT
                report_id AS item_id,
                'report' AS kind,
                watch_id,
                watch_session_id,
                NULL AS cycle,
                created_at,
                status,
                NULL AS incident_count,
                NULL AS tool_count,
                NULL AS blocked_count,
                NULL AS input_tokens,
                NULL AS output_tokens,
                NULL AS total_tokens,
                report_json AS payload_json
            FROM watch_reports
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*values, *values, per_page, offset],
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Watch Commands ---

    async def insert_watch_command(self, command: str, payload: str | None = None) -> int:
        """Insert a watch command and return its ID."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "INSERT INTO watch_commands (command, payload, created_at) VALUES (?, ?, ?)",
            (command, payload, now),
        )
        await conn.commit()
        return cursor.lastrowid

    async def get_pending_watch_commands(self) -> list[dict]:
        """Get all pending watch commands in order."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM watch_commands WHERE status = 'pending' ORDER BY id",
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_watch_command_status(self, cmd_id: int, status: str, error: str | None = None) -> None:
        """Update a watch command's status."""
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE watch_commands SET status = ?, error = ? WHERE id = ?",
            (status, error, cmd_id),
        )
        await conn.commit()

    # --- Watch Approvals ---

    async def insert_watch_approval(
        self,
        *,
        request_id: str,
        tool_name: str,
        args: str | None = None,
        risk_level: int,
    ) -> int:
        """Insert a watch approval request."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            """
            INSERT INTO watch_approvals (request_id, tool_name, args, risk_level, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, tool_name, args, risk_level, now),
        )
        await conn.commit()
        return cursor.lastrowid

    async def get_watch_approval(self, request_id: str) -> dict | None:
        """Get a watch approval by request_id."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM watch_approvals WHERE request_id = ?",
            (request_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_watch_approval(self, request_id: str, status: str) -> None:
        """Update a watch approval's status."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            "UPDATE watch_approvals SET status = ?, responded_at = ? WHERE request_id = ?",
            (status, now, request_id),
        )
        await conn.commit()

    async def cleanup_watch_data(self, max_cycles: int = 500) -> int:
        """Remove old watch events, commands, and approvals beyond retention."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT cycle_id FROM watch_cycles ORDER BY started_at DESC LIMIT ?", (max_cycles,))
        rows = await cursor.fetchall()
        if not rows:
            return 0
        keep_ids = [row[0] for row in rows if row[0]]
        placeholders = ",".join("?" for _ in keep_ids) or "''"
        cursor = await conn.execute(
            f"DELETE FROM watch_events WHERE cycle_id IS NOT NULL AND cycle_id NOT IN ({placeholders})",
            keep_ids,
        )
        deleted_events = cursor.rowcount
        cursor = await conn.execute(
            f"DELETE FROM watch_cycles WHERE cycle_id NOT IN ({placeholders})",
            keep_ids,
        )
        deleted_cycles = cursor.rowcount

        await conn.execute(
            "DELETE FROM watch_commands WHERE id NOT IN (SELECT id FROM watch_commands ORDER BY id DESC LIMIT 1000)"
        )
        await conn.execute(
            "DELETE FROM watch_approvals WHERE id NOT IN (SELECT id FROM watch_approvals ORDER BY id DESC LIMIT 1000)"
        )
        await conn.commit()
        return deleted_events + deleted_cycles

    # --- Managed Hosts ---

    async def save_managed_host(
        self,
        *,
        name: str,
        address: str,
        key_file: str,
        status: str = "active",
        user: str = "root",
        port: int = 22,
        tags: list[str] | None = None,
        services: list[str] | None = None,
        service_root: str = "/opt",
    ) -> None:
        """Insert or update a managed host, preserving created_at on conflict."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            """
            INSERT INTO managed_hosts
                (name, address, user, port, key_file, tags, services, service_root, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                address = excluded.address,
                user = excluded.user,
                port = excluded.port,
                key_file = excluded.key_file,
                tags = excluded.tags,
                services = excluded.services,
                service_root = excluded.service_root,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                name,
                address,
                user,
                port,
                key_file,
                json.dumps(tags or []),
                json.dumps(services or []),
                service_root,
                status,
                now,
                now,
            ),
        )
        await conn.commit()

    async def list_managed_hosts(self) -> list[dict]:
        """List all managed hosts."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM managed_hosts ORDER BY name")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_managed_host(self, name: str) -> dict | None:
        """Get a managed host by name."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM managed_hosts WHERE name = ?", (name,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_managed_host(self, name: str) -> bool:
        """Delete a managed host by name. Returns True if deleted."""
        conn = await self._get_conn()
        cursor = await conn.execute("DELETE FROM managed_hosts WHERE name = ?", (name,))
        await conn.commit()
        return cursor.rowcount > 0

    async def update_managed_host_status(self, name: str, status: str) -> bool:
        """Update a managed host's status. Returns True if updated."""
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "UPDATE managed_hosts SET status = ?, updated_at = ? WHERE name = ?",
            (status, now, name),
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
