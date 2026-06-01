"""SQLite database operations using aiosqlite."""

import json
import os
from datetime import datetime
from typing import Any

import aiosqlite

from ..models.alert import Alert, AlertSeverity, AlertType
from ..models.progress_event import ProgressEvent
from ..models.session import Session, SessionStatus
from ..utils.logging import get_logger

logger = get_logger("app.storage.database")


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    async def initialize(self) -> None:
        """Initialize database tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._create_tables(db)
            await db.commit()
        logger.info("Database initialized", extra={"db_path": self.db_path})

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create all database tables."""
        # Sessions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                adapter TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # Progress events table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS progress_events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                detail TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

        # Alerts table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                session_id TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                acknowledged BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
            )
        """)

        # Authorized chats table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS authorized_chats (
                chat_id INTEGER PRIMARY KEY,
                name TEXT,
                added_at TEXT NOT NULL
            )
        """)

        # Create indexes for better query performance
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_status
            ON sessions(status)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_progress_events_session_id
            ON progress_events(session_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_progress_events_timestamp
            ON progress_events(timestamp)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_session_id
            ON alerts(session_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
            ON alerts(timestamp)
        """)

    # Session operations

    async def create_session(self, session: Session) -> None:
        """Create a new session."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO sessions (id, name, status, adapter, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id,
                session.name,
                session.status.value,
                session.adapter,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                json.dumps(session.metadata),
            ))
            await db.commit()
        logger.info("Created session", extra={"session_id": session.id, "name": session.name})

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, name, status, adapter, created_at, updated_at, metadata
                FROM sessions WHERE id = ?
            """, (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Session(
                        id=row[0],
                        name=row[1],
                        status=SessionStatus(row[2]),
                        adapter=row[3],
                        created_at=datetime.fromisoformat(row[4]),
                        updated_at=datetime.fromisoformat(row[5]),
                        metadata=json.loads(row[6]),
                    )
        return None

    async def update_session(self, session: Session) -> bool:
        """Update a session."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE sessions
                SET name = ?, status = ?, adapter = ?, updated_at = ?, metadata = ?
                WHERE id = ?
            """, (
                session.name,
                session.status.value,
                session.adapter,
                session.updated_at.isoformat(),
                json.dumps(session.metadata),
                session.id,
            ))
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info("Updated session", extra={"session_id": session.id})
            return success

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its related data."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info("Deleted session", extra={"session_id": session_id})
            return success

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        status: SessionStatus | None = None,
    ) -> list[Session]:
        """List sessions with optional filtering."""
        query = """
            SELECT id, name, status, adapter, created_at, updated_at, metadata
            FROM sessions
        """
        params: list[Any] = []

        if status:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        sessions = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                async for row in cursor:
                    sessions.append(Session(
                        id=row[0],
                        name=row[1],
                        status=SessionStatus(row[2]),
                        adapter=row[3],
                        created_at=datetime.fromisoformat(row[4]),
                        updated_at=datetime.fromisoformat(row[5]),
                        metadata=json.loads(row[6]),
                    ))
        return sessions

    async def get_active_session(self) -> Session | None:
        """Get the currently active session."""
        sessions = await self.list_sessions(limit=1, status=SessionStatus.ACTIVE)
        return sessions[0] if sessions else None

    # Progress event operations

    async def create_progress_event(self, event: ProgressEvent) -> None:
        """Create a new progress event."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO progress_events (id, session_id, stage, detail, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event.id,
                event.session_id,
                event.stage,
                event.detail,
                event.timestamp.isoformat(),
                json.dumps(event.metadata),
            ))
            await db.commit()
        logger.debug("Created progress event", extra={
            "event_id": event.id,
            "session_id": event.session_id,
            "stage": event.stage
        })

    async def get_progress_events(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProgressEvent]:
        """Get progress events for a session."""
        events = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, session_id, stage, detail, timestamp, metadata
                FROM progress_events
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (session_id, limit, offset)) as cursor:
                async for row in cursor:
                    events.append(ProgressEvent(
                        id=row[0],
                        session_id=row[1],
                        stage=row[2],
                        detail=row[3],
                        timestamp=datetime.fromisoformat(row[4]),
                        metadata=json.loads(row[5]),
                    ))
        return events

    async def get_recent_progress_events(
        self,
        session_id: str,
        minutes: int = 30,
    ) -> list[ProgressEvent]:
        """Get recent progress events for a session."""
        cutoff = datetime.utcnow().replace(microsecond=0)
        cutoff_timestamp = cutoff.replace(
            minute=cutoff.minute - minutes if cutoff.minute >= minutes else 0
        )

        events = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, session_id, stage, detail, timestamp, metadata
                FROM progress_events
                WHERE session_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (session_id, cutoff_timestamp.isoformat())) as cursor:
                async for row in cursor:
                    events.append(ProgressEvent(
                        id=row[0],
                        session_id=row[1],
                        stage=row[2],
                        detail=row[3],
                        timestamp=datetime.fromisoformat(row[4]),
                        metadata=json.loads(row[5]),
                    ))
        return events

    # Alert operations

    async def create_alert(self, alert: Alert) -> None:
        """Create a new alert."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO alerts (id, type, severity, message, session_id, timestamp, metadata, acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.id,
                alert.type.value,
                alert.severity.value,
                alert.message,
                alert.session_id,
                alert.timestamp.isoformat(),
                json.dumps(alert.metadata),
                alert.acknowledged,
            ))
            await db.commit()
        logger.info("Created alert", extra={
            "alert_id": alert.id,
            "type": alert.type.value,
            "severity": alert.severity.value,
            "session_id": alert.session_id
        })

    async def get_alert(self, alert_id: str) -> Alert | None:
        """Get an alert by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, type, severity, message, session_id, timestamp, metadata, acknowledged
                FROM alerts WHERE id = ?
            """, (alert_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Alert(
                        id=row[0],
                        type=AlertType(row[1]),
                        severity=AlertSeverity(row[2]),
                        message=row[3],
                        session_id=row[4],
                        timestamp=datetime.fromisoformat(row[5]),
                        metadata=json.loads(row[6]),
                        acknowledged=bool(row[7]),
                    )
        return None

    async def update_alert(self, alert: Alert) -> bool:
        """Update an alert."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE alerts
                SET type = ?, severity = ?, message = ?, session_id = ?, timestamp = ?,
                    metadata = ?, acknowledged = ?
                WHERE id = ?
            """, (
                alert.type.value,
                alert.severity.value,
                alert.message,
                alert.session_id,
                alert.timestamp.isoformat(),
                json.dumps(alert.metadata),
                alert.acknowledged,
                alert.id,
            ))
            await db.commit()
            return cursor.rowcount > 0

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE alerts SET acknowledged = TRUE WHERE id = ?
            """, (alert_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def list_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        session_id: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[Alert]:
        """List alerts with optional filtering."""
        query = """
            SELECT id, type, severity, message, session_id, timestamp, metadata, acknowledged
            FROM alerts
        """
        params: list[Any] = []
        conditions = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if acknowledged is not None:
            conditions.append("acknowledged = ?")
            params.append(acknowledged)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        alerts = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                async for row in cursor:
                    alerts.append(Alert(
                        id=row[0],
                        type=AlertType(row[1]),
                        severity=AlertSeverity(row[2]),
                        message=row[3],
                        session_id=row[4],
                        timestamp=datetime.fromisoformat(row[5]),
                        metadata=json.loads(row[6]),
                        acknowledged=bool(row[7]),
                    ))
        return alerts

    # Authorized chat operations

    async def add_authorized_chat(self, chat_id: int, name: str | None = None) -> None:
        """Add an authorized chat."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO authorized_chats (chat_id, name, added_at)
                VALUES (?, ?, ?)
            """, (chat_id, name, datetime.utcnow().isoformat()))
            await db.commit()
        logger.info("Added authorized chat", extra={"chat_id": chat_id, "name": name})

    async def remove_authorized_chat(self, chat_id: int) -> bool:
        """Remove an authorized chat."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM authorized_chats WHERE chat_id = ?
            """, (chat_id,))
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info("Removed authorized chat", extra={"chat_id": chat_id})
            return success

    async def is_chat_authorized(self, chat_id: int) -> bool:
        """Check if a chat is authorized."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 1 FROM authorized_chats WHERE chat_id = ?
            """, (chat_id,)) as cursor:
                return await cursor.fetchone() is not None

    async def list_authorized_chats(self) -> list[dict[str, Any]]:
        """List all authorized chats."""
        chats = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT chat_id, name, added_at FROM authorized_chats ORDER BY added_at DESC
            """) as cursor:
                async for row in cursor:
                    chats.append({
                        "chat_id": row[0],
                        "name": row[1],
                        "added_at": row[2],
                    })
        return chats

    # Maintenance operations

    async def cleanup_old_data(self, days: int = 30) -> dict[str, int]:
        """Clean up old data older than specified days."""
        cutoff = datetime.utcnow().replace(
            day=datetime.utcnow().day - days if datetime.utcnow().day > days else 1
        )
        cutoff_iso = cutoff.isoformat()

        counts = {"progress_events": 0, "alerts": 0, "sessions": 0}

        async with aiosqlite.connect(self.db_path) as db:
            # Clean up old progress events
            cursor = await db.execute("""
                DELETE FROM progress_events WHERE timestamp < ?
            """, (cutoff_iso,))
            counts["progress_events"] = cursor.rowcount

            # Clean up old alerts
            cursor = await db.execute("""
                DELETE FROM alerts WHERE timestamp < ? AND acknowledged = TRUE
            """, (cutoff_iso,))
            counts["alerts"] = cursor.rowcount

            # Clean up old completed sessions
            cursor = await db.execute("""
                DELETE FROM sessions
                WHERE status IN ('completed', 'error') AND updated_at < ?
            """, (cutoff_iso,))
            counts["sessions"] = cursor.rowcount

            await db.commit()

        logger.info("Cleaned up old data", extra={"cutoff_days": days, "counts": counts})
        return counts

    async def get_database_stats(self) -> dict[str, int]:
        """Get database statistics."""
        stats = {}
        async with aiosqlite.connect(self.db_path) as db:
            # Count sessions
            async with db.execute("SELECT COUNT(*) FROM sessions") as cursor:
                stats["sessions"] = (await cursor.fetchone())[0]

            # Count progress events
            async with db.execute("SELECT COUNT(*) FROM progress_events") as cursor:
                stats["progress_events"] = (await cursor.fetchone())[0]

            # Count alerts
            async with db.execute("SELECT COUNT(*) FROM alerts") as cursor:
                stats["alerts"] = (await cursor.fetchone())[0]

            # Count authorized chats
            async with db.execute("SELECT COUNT(*) FROM authorized_chats") as cursor:
                stats["authorized_chats"] = (await cursor.fetchone())[0]

        return stats

    async def close(self) -> None:
        """Close database connections. No-op for aiosqlite, connections are short-lived."""
        logger.debug("Database close requested (aiosqlite connections are managed per-operation)")