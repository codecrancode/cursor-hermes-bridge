"""Progress tracking service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..models.alert import Alert, AlertSeverity, AlertType
from ..models.progress_event import ProgressEvent
from ..storage.database import Database
from ..storage.jsonl_export import JSONLExporter
from ..utils.config import settings
from ..utils.logging import get_logger

logger = get_logger("app.services.progress_service")


class ProgressService:
    """Service for tracking and managing progress events."""

    def __init__(self, database: Database, jsonl_exporter: JSONLExporter | None = None) -> None:
        self.database = database
        self.jsonl_exporter = jsonl_exporter
        self._alert_handlers: list[callable] = []

    def add_alert_handler(self, handler: callable) -> None:
        """Add a handler to be called when alerts are created.

        Args:
            handler: Async function that accepts an Alert object
        """
        self._alert_handlers.append(handler)

    async def create_progress_event(
        self,
        session_id: str,
        stage: str,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProgressEvent:
        """Create a new progress event.

        Args:
            session_id: The session this event belongs to
            stage: The stage/phase of progress
            detail: Detailed description of what happened
            metadata: Additional metadata for the event

        Returns:
            The created progress event
        """
        event = ProgressEvent.create_new(
            session_id=session_id,
            stage=stage,
            detail=detail,
            metadata=metadata or {}
        )

        # Store in database
        await self.database.create_progress_event(event)

        # Export to JSONL if enabled
        if self.jsonl_exporter:
            await self.jsonl_exporter.export_progress_event(event)

        # Check for alert triggers
        await self._check_alert_triggers(event)

        logger.debug("Created progress event", extra={
            "event_id": event.id,
            "session_id": session_id,
            "stage": stage
        })

        return event

    async def get_progress_events(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProgressEvent]:
        """Get progress events for a session.

        Args:
            session_id: The session to get progress for
            limit: Maximum number of events to return
            offset: Number of events to skip

        Returns:
            List of progress events, ordered by timestamp (most recent first)
        """
        return await self.database.get_progress_events(session_id, limit, offset)

    async def get_recent_progress_events(
        self,
        session_id: str,
        minutes: int = 30,
    ) -> list[ProgressEvent]:
        """Get recent progress events for a session.

        Args:
            session_id: The session to get progress for
            minutes: Number of minutes back to look

        Returns:
            List of recent progress events
        """
        return await self.database.get_recent_progress_events(session_id, minutes)

    async def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """Get a summary of progress for a session.

        Args:
            session_id: The session to summarize

        Returns:
            Dictionary containing progress summary
        """
        events = await self.get_progress_events(session_id, limit=1000)

        # Count events by stage
        stage_counts: dict[str, int] = {}
        for event in events:
            stage_counts[event.stage] = stage_counts.get(event.stage, 0) + 1

        # Find latest events by stage
        latest_by_stage: dict[str, ProgressEvent] = {}
        for event in events:
            if (
                event.stage not in latest_by_stage or
                event.timestamp > latest_by_stage[event.stage].timestamp
            ):
                latest_by_stage[event.stage] = event

        # Check for errors and completions
        error_events = [e for e in events if e.has_error()]
        completion_events = [e for e in events if e.is_completion()]
        approval_events = [e for e in events if e.needs_approval()]

        # Calculate time span
        if events:
            start_time = min(e.timestamp for e in events)
            end_time = max(e.timestamp for e in events)
            duration = end_time - start_time
        else:
            start_time = None
            end_time = None
            duration = timedelta(0)

        return {
            "session_id": session_id,
            "total_events": len(events),
            "stage_counts": stage_counts,
            "latest_by_stage": {
                stage: {
                    "detail": event.detail,
                    "timestamp": event.timestamp.isoformat(),
                    "event_id": event.id
                }
                for stage, event in latest_by_stage.items()
            },
            "error_count": len(error_events),
            "completion_count": len(completion_events),
            "approval_needed_count": len(approval_events),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "duration_seconds": duration.total_seconds(),
            "current_stage": latest_by_stage.get("current", {}).get("stage") if latest_by_stage else None,
        }

    async def create_alert(
        self,
        alert_type: AlertType | str,
        severity: AlertSeverity | str,
        message: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Create a new alert.

        Args:
            alert_type: Type of alert
            severity: Severity level
            message: Alert message
            session_id: Optional session this alert relates to
            metadata: Additional metadata

        Returns:
            The created alert
        """
        alert = Alert.create_new(
            alert_type=alert_type,
            severity=severity,
            message=message,
            session_id=session_id,
            metadata=metadata or {}
        )

        # Store in database
        await self.database.create_alert(alert)

        # Export to JSONL if enabled
        if self.jsonl_exporter:
            await self.jsonl_exporter.export_alert(alert)

        # Notify handlers
        await self._notify_alert_handlers(alert)

        logger.info("Created alert", extra={
            "alert_id": alert.id,
            "type": alert.type.value,
            "severity": alert.severity.value,
            "session_id": session_id
        })

        return alert

    async def get_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        session_id: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[Alert]:
        """Get alerts with optional filtering.

        Args:
            limit: Maximum number of alerts to return
            offset: Number of alerts to skip
            session_id: Filter by session ID
            acknowledged: Filter by acknowledgment status

        Returns:
            List of alerts
        """
        return await self.database.list_alerts(limit, offset, session_id, acknowledged)

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: The alert ID to acknowledge

        Returns:
            True if successful, False if alert not found
        """
        success = await self.database.acknowledge_alert(alert_id)
        if success:
            logger.info("Acknowledged alert", extra={"alert_id": alert_id})
        return success

    async def check_inactivity_timeouts(self) -> list[Alert]:
        """Check for sessions that have been inactive and create timeout alerts.

        Returns:
            List of timeout alerts created
        """
        timeout_minutes = settings.PROGRESS_INACTIVITY_TIMEOUT_MINUTES
        cutoff_time = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        # Get all active/paused sessions
        from .session_service import SessionService  # Import here to avoid circular import
        from ..models.session import SessionStatus

        # We would need the session service instance here
        # For now, we'll implement a simpler check
        alerts = []

        try:
            # This is a simplified implementation
            # In practice, you'd inject the session service or query sessions differently
            logger.debug("Checking inactivity timeouts", extra={
                "timeout_minutes": timeout_minutes,
                "cutoff_time": cutoff_time.isoformat()
            })

            # TODO: Implement proper inactivity checking with session service
            # For now, return empty list

        except Exception as e:
            logger.error("Error checking inactivity timeouts", extra={"error": str(e)})

        return alerts

    async def _check_alert_triggers(self, event: ProgressEvent) -> None:
        """Check if a progress event should trigger any alerts."""
        alerts_to_create = []

        # Check for error events
        if event.has_error():
            alerts_to_create.append({
                "type": AlertType.TASK_ERROR,
                "severity": AlertSeverity.ERROR,
                "message": f"Error in {event.stage}: {event.detail}",
                "session_id": event.session_id,
                "metadata": {"event_id": event.id}
            })

        # Check for completion events
        if event.is_completion():
            alerts_to_create.append({
                "type": AlertType.TASK_COMPLETE,
                "severity": AlertSeverity.INFO,
                "message": f"Task completed: {event.detail}",
                "session_id": event.session_id,
                "metadata": {"event_id": event.id}
            })

        # Check for approval needed events
        if event.needs_approval():
            alerts_to_create.append({
                "type": AlertType.APPROVAL_NEEDED,
                "severity": AlertSeverity.WARNING,
                "message": f"Approval needed: {event.detail}",
                "session_id": event.session_id,
                "metadata": {"event_id": event.id}
            })

        # Create the alerts
        for alert_data in alerts_to_create:
            await self.create_alert(**alert_data)

    async def _notify_alert_handlers(self, alert: Alert) -> None:
        """Notify all registered alert handlers."""
        for handler in self._alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error("Error in alert handler", extra={
                    "alert_id": alert.id,
                    "handler": str(handler),
                    "error": str(e)
                })

    async def get_progress_statistics(self) -> dict[str, Any]:
        """Get statistics about progress events and alerts.

        Returns:
            Dictionary with progress statistics
        """
        # Get database stats
        db_stats = await self.database.get_database_stats()

        # Calculate additional stats
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)

        stats = {
            "total_progress_events": db_stats.get("progress_events", 0),
            "total_alerts": db_stats.get("alerts", 0),
            "alert_handlers_count": len(self._alert_handlers),
            "jsonl_export_enabled": self.jsonl_exporter is not None,
        }

        # Add JSONL export stats if available
        if self.jsonl_exporter:
            try:
                export_stats = await self.jsonl_exporter.get_export_stats()
                stats["jsonl_export"] = export_stats
            except Exception as e:
                logger.warning("Error getting JSONL export stats", extra={"error": str(e)})

        return stats

    async def cleanup_old_data(self, days: int = 30) -> dict[str, int]:
        """Clean up old progress events and alerts.

        Args:
            days: Number of days of data to keep

        Returns:
            Dictionary with cleanup statistics
        """
        return await self.database.cleanup_old_data(days)

    async def export_progress_batch(
        self,
        session_id: str | None = None,
        limit: int = 1000
    ) -> int:
        """Export a batch of progress events to JSONL.

        Args:
            session_id: Specific session to export (None for all)
            limit: Maximum number of events to export

        Returns:
            Number of events exported
        """
        if not self.jsonl_exporter:
            return 0

        try:
            if session_id:
                events = await self.get_progress_events(session_id, limit=limit)
            else:
                # Get events from all sessions
                # This is a simplified implementation
                events = []

            if events:
                count = await self.jsonl_exporter.export_progress_events_batch(events)
                logger.info("Exported progress events batch", extra={
                    "session_id": session_id,
                    "count": count
                })
                return count

        except Exception as e:
            logger.error("Error exporting progress batch", extra={
                "session_id": session_id,
                "error": str(e)
            })

        return 0