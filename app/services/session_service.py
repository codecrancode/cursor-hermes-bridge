"""Session management service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..adapters.base import CursorAdapter, adapter_registry
from ..models.session import Session, SessionStatus
from ..storage.database import Database
from ..utils.logging import get_logger

logger = get_logger("app.services.session_service")


class SessionService:
    """Service for managing Cursor sessions."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._active_session_id: str | None = None

    async def create_session(
        self,
        name: str,
        adapter_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new session.

        Args:
            name: Name for the new session
            adapter_name: Specific adapter to use (None for primary)
            metadata: Additional metadata for the session

        Returns:
            The created session

        Raises:
            ValueError: If the specified adapter is not available
        """
        # Get the adapter to use
        if adapter_name:
            adapter = adapter_registry.get(adapter_name)
            if not adapter or not adapter.is_available():
                raise ValueError(f"Adapter '{adapter_name}' is not available")
            actual_adapter_name = adapter_name
        else:
            adapter = adapter_registry.get_primary()
            if not adapter:
                raise ValueError("No primary adapter available")
            actual_adapter_name = adapter.name

        # Create session object
        session = Session.create_new(
            name=name,
            adapter=actual_adapter_name,
            metadata=metadata or {}
        )

        # Store in database
        await self.database.create_session(session)

        logger.info("Created new session", extra={
            "session_id": session.id,
            "name": name,
            "adapter": actual_adapter_name
        })

        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID.

        Args:
            session_id: The session ID to retrieve

        Returns:
            The session object or None if not found
        """
        return await self.database.get_session(session_id)

    async def update_session(self, session: Session) -> bool:
        """Update a session in the database.

        Args:
            session: The session to update

        Returns:
            True if the session was updated, False if not found
        """
        return await self.database.update_session(session)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its data.

        Args:
            session_id: The session ID to delete

        Returns:
            True if the session was deleted, False if not found
        """
        # Clear active session if this was it
        if self._active_session_id == session_id:
            self._active_session_id = None

        success = await self.database.delete_session(session_id)

        if success:
            logger.info("Deleted session", extra={"session_id": session_id})

        return success

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        status: SessionStatus | None = None,
    ) -> list[Session]:
        """List sessions with optional filtering.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            status: Filter by session status

        Returns:
            List of session objects
        """
        return await self.database.list_sessions(limit, offset, status)

    async def get_active_session(self) -> Session | None:
        """Get the currently active session.

        Returns:
            The active session or None if no session is active
        """
        # First check our cached active session
        if self._active_session_id:
            session = await self.get_session(self._active_session_id)
            if session and session.status == SessionStatus.ACTIVE:
                return session

        # Fall back to database lookup
        session = await self.database.get_active_session()
        if session:
            self._active_session_id = session.id

        return session

    async def set_active_session(self, session_id: str) -> bool:
        """Set a session as the active session.

        Args:
            session_id: The session ID to make active

        Returns:
            True if successful, False if session not found

        Raises:
            ValueError: If the session doesn't exist
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        # Deactivate current active session if any
        current_active = await self.get_active_session()
        if current_active and current_active.id != session_id:
            current_active.update_status(SessionStatus.PAUSED)
            await self.update_session(current_active)

        # Activate the new session
        session.update_status(SessionStatus.ACTIVE)
        success = await self.update_session(session)

        if success:
            self._active_session_id = session_id
            logger.info("Set active session", extra={"session_id": session_id})

        return success

    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        metadata_updates: dict[str, Any] | None = None,
    ) -> bool:
        """Update a session's status and optionally its metadata.

        Args:
            session_id: The session ID to update
            status: The new status
            metadata_updates: Optional metadata updates

        Returns:
            True if successful, False if session not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False

        session.update_status(status)
        if metadata_updates:
            session.update_metadata(metadata_updates)

        success = await self.update_session(session)

        if success:
            # Update active session tracking
            if status == SessionStatus.ACTIVE:
                self._active_session_id = session_id
            elif self._active_session_id == session_id and status != SessionStatus.ACTIVE:
                self._active_session_id = None

            logger.info("Updated session status", extra={
                "session_id": session_id,
                "new_status": status.value
            })

        return success

    async def pause_session(self, session_id: str) -> bool:
        """Pause a session.

        Args:
            session_id: The session ID to pause

        Returns:
            True if successful, False if session not found
        """
        return await self.update_session_status(session_id, SessionStatus.PAUSED)

    async def resume_session(self, session_id: str) -> bool:
        """Resume a paused session.

        Args:
            session_id: The session ID to resume

        Returns:
            True if successful, False if session not found
        """
        return await self.set_active_session(session_id)

    async def complete_session(self, session_id: str) -> bool:
        """Mark a session as completed.

        Args:
            session_id: The session ID to complete

        Returns:
            True if successful, False if session not found
        """
        return await self.update_session_status(session_id, SessionStatus.COMPLETED)

    async def mark_session_error(
        self,
        session_id: str,
        error_message: str
    ) -> bool:
        """Mark a session as having an error.

        Args:
            session_id: The session ID to mark as error
            error_message: Description of the error

        Returns:
            True if successful, False if session not found
        """
        return await self.update_session_status(
            session_id,
            SessionStatus.ERROR,
            {"error_message": error_message, "error_timestamp": str(datetime.utcnow())}
        )

    async def get_session_adapter(self, session_id: str) -> CursorAdapter | None:
        """Get the adapter associated with a session.

        Args:
            session_id: The session ID

        Returns:
            The adapter instance or None if not found/available
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        adapter = adapter_registry.get(session.adapter)
        if adapter and adapter.is_available():
            return adapter

        return None

    async def sync_with_adapter(self, adapter_name: str | None = None) -> dict[str, int]:
        """Sync local session state with an adapter.

        Args:
            adapter_name: Specific adapter to sync with (None for primary)

        Returns:
            Dictionary with sync statistics
        """
        # Get adapter
        if adapter_name:
            adapter = adapter_registry.get(adapter_name)
        else:
            adapter = adapter_registry.get_primary()

        if not adapter or not adapter.is_available():
            logger.warning("Cannot sync - adapter not available", extra={
                "adapter_name": adapter_name
            })
            return {"created": 0, "updated": 0, "errors": 0}

        stats = {"created": 0, "updated": 0, "errors": 0}

        try:
            # Get sessions from adapter
            adapter_sessions = await adapter.list_sessions()

            for adapter_session in adapter_sessions:
                try:
                    # Check if session exists in database
                    existing_session = await self.get_session(adapter_session.id)

                    if existing_session:
                        # Update if the adapter session is newer
                        if adapter_session.updated_at > existing_session.updated_at:
                            existing_session.status = adapter_session.status
                            existing_session.updated_at = adapter_session.updated_at
                            existing_session.metadata.update(adapter_session.metadata)
                            await self.update_session(existing_session)
                            stats["updated"] += 1
                    else:
                        # Create new session
                        await self.database.create_session(adapter_session)
                        stats["created"] += 1

                except Exception as e:
                    logger.error("Error syncing session", extra={
                        "session_id": adapter_session.id,
                        "error": str(e)
                    })
                    stats["errors"] += 1

            logger.info("Synced sessions with adapter", extra={
                "adapter": adapter.name,
                "stats": stats
            })

        except Exception as e:
            logger.error("Error syncing with adapter", extra={
                "adapter": adapter.name if adapter else None,
                "error": str(e)
            })

        return stats

    async def cleanup_old_sessions(self, days: int = 30) -> dict[str, int]:
        """Clean up old completed/error sessions.

        Args:
            days: Number of days to keep sessions

        Returns:
            Dictionary with cleanup statistics
        """
        # Use database cleanup method
        return await self.database.cleanup_old_data(days)

    async def get_session_statistics(self) -> dict[str, Any]:
        """Get statistics about sessions.

        Returns:
            Dictionary with session statistics
        """
        all_sessions = await self.list_sessions(limit=1000)  # Get a large sample

        stats = {
            "total": len(all_sessions),
            "by_status": {},
            "by_adapter": {},
            "active_session_id": self._active_session_id,
        }

        for session in all_sessions:
            # Count by status
            status_key = session.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

            # Count by adapter
            adapter_key = session.adapter
            stats["by_adapter"][adapter_key] = stats["by_adapter"].get(adapter_key, 0) + 1

        return stats