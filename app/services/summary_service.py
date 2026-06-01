"""Summary service for generating human-readable summaries."""

from __future__ import annotations

from typing import Any

from ..models.progress_event import ProgressEvent
from ..models.session import Session
from ..utils.config import settings
from ..utils.logging import get_logger

logger = get_logger("app.services.summary_service")


class SummaryService:
    """Service for generating human-readable summaries from progress events."""

    def __init__(self, summarizer: Any = None) -> None:
        self.summarizer = summarizer
        if not summarizer:
            self._initialize_default_summarizer()

    def _initialize_default_summarizer(self) -> None:
        """Initialize the default summarizer based on configuration."""
        summarizer_type = settings.SUMMARIZER_TYPE

        if summarizer_type == "local":
            from ..summarizers.local_summarizer import LocalSummarizer
            self.summarizer = LocalSummarizer()
        else:
            logger.warning("Unknown summarizer type, using local", extra={
                "requested_type": summarizer_type
            })
            from ..summarizers.local_summarizer import LocalSummarizer
            self.summarizer = LocalSummarizer()

    async def summarize_session(self, session: Session, events: list[ProgressEvent]) -> str:
        """Generate a summary for a session and its progress events.

        Args:
            session: The session to summarize
            events: Progress events for the session

        Returns:
            Human-readable summary string
        """
        try:
            summary = await self.summarizer.summarize_session(session, events)
            logger.debug("Generated session summary", extra={
                "session_id": session.id,
                "events_count": len(events),
                "summary_length": len(summary)
            })
            return summary
        except Exception as e:
            logger.error("Error generating session summary", extra={
                "session_id": session.id,
                "error": str(e)
            })
            return f"Error generating summary: {str(e)}"

    async def summarize_recent_activity(
        self,
        session: Session,
        events: list[ProgressEvent],
        minutes: int = 30
    ) -> str:
        """Generate a summary of recent activity for a session.

        Args:
            session: The session to summarize
            events: Recent progress events
            minutes: Number of minutes of recent activity covered

        Returns:
            Human-readable summary of recent activity
        """
        try:
            summary = await self.summarizer.summarize_recent_activity(session, events, minutes)
            logger.debug("Generated recent activity summary", extra={
                "session_id": session.id,
                "events_count": len(events),
                "minutes": minutes
            })
            return summary
        except Exception as e:
            logger.error("Error generating recent activity summary", extra={
                "session_id": session.id,
                "error": str(e)
            })
            return f"Error generating recent activity summary: {str(e)}"

    async def summarize_progress_events(self, events: list[ProgressEvent]) -> str:
        """Generate a summary from a list of progress events.

        Args:
            events: Progress events to summarize

        Returns:
            Human-readable summary string
        """
        try:
            summary = await self.summarizer.summarize_events(events)
            logger.debug("Generated events summary", extra={
                "events_count": len(events),
                "summary_length": len(summary)
            })
            return summary
        except Exception as e:
            logger.error("Error generating events summary", extra={
                "events_count": len(events),
                "error": str(e)
            })
            return f"Error generating summary: {str(e)}"

    async def generate_status_message(
        self,
        session: Session | None,
        recent_events: list[ProgressEvent]
    ) -> str:
        """Generate a concise status message suitable for Telegram.

        Args:
            session: Current session (None if no active session)
            recent_events: Recent progress events

        Returns:
            Concise status message
        """
        try:
            if not session:
                return "No active session"

            if not recent_events:
                return f"Session '{session.name}' ({session.status.value}) - No recent activity"

            # Use summarizer to generate status
            if hasattr(self.summarizer, 'generate_status_message'):
                message = await self.summarizer.generate_status_message(session, recent_events)
            else:
                # Fallback to basic status
                latest_event = recent_events[0] if recent_events else None
                if latest_event:
                    message = f"Session '{session.name}' ({session.status.value})\n"
                    message += f"Latest: {latest_event.stage} - {latest_event.detail}"
                else:
                    message = f"Session '{session.name}' ({session.status.value}) - No recent events"

            logger.debug("Generated status message", extra={
                "session_id": session.id if session else None,
                "events_count": len(recent_events)
            })
            return message

        except Exception as e:
            logger.error("Error generating status message", extra={
                "session_id": session.id if session else None,
                "error": str(e)
            })
            return f"Error generating status: {str(e)}"

    async def generate_completion_message(
        self,
        session: Session,
        completion_event: ProgressEvent
    ) -> str:
        """Generate a completion notification message.

        Args:
            session: The session that completed
            completion_event: The completion event

        Returns:
            Completion notification message
        """
        try:
            if hasattr(self.summarizer, 'generate_completion_message'):
                message = await self.summarizer.generate_completion_message(session, completion_event)
            else:
                # Fallback implementation
                message = f"✅ Task completed in session '{session.name}'\n"
                message += f"Details: {completion_event.detail}"

            logger.debug("Generated completion message", extra={
                "session_id": session.id,
                "event_id": completion_event.id
            })
            return message

        except Exception as e:
            logger.error("Error generating completion message", extra={
                "session_id": session.id,
                "error": str(e)
            })
            return f"Task completed in session '{session.name}' (details unavailable)"

    async def generate_error_message(
        self,
        session: Session,
        error_event: ProgressEvent
    ) -> str:
        """Generate an error notification message.

        Args:
            session: The session where the error occurred
            error_event: The error event

        Returns:
            Error notification message
        """
        try:
            if hasattr(self.summarizer, 'generate_error_message'):
                message = await self.summarizer.generate_error_message(session, error_event)
            else:
                # Fallback implementation
                message = f"❌ Error in session '{session.name}'\n"
                message += f"Stage: {error_event.stage}\n"
                message += f"Details: {error_event.detail}"

            logger.debug("Generated error message", extra={
                "session_id": session.id,
                "event_id": error_event.id
            })
            return message

        except Exception as e:
            logger.error("Error generating error message", extra={
                "session_id": session.id,
                "error": str(e)
            })
            return f"Error occurred in session '{session.name}' (details unavailable)"

    async def generate_approval_message(
        self,
        session: Session,
        approval_event: ProgressEvent
    ) -> str:
        """Generate an approval needed notification message.

        Args:
            session: The session requiring approval
            approval_event: The approval event

        Returns:
            Approval notification message
        """
        try:
            if hasattr(self.summarizer, 'generate_approval_message'):
                message = await self.summarizer.generate_approval_message(session, approval_event)
            else:
                # Fallback implementation
                message = f"⏸️ Approval needed in session '{session.name}'\n"
                message += f"Stage: {approval_event.stage}\n"
                message += f"Details: {approval_event.detail}"

            logger.debug("Generated approval message", extra={
                "session_id": session.id,
                "event_id": approval_event.id
            })
            return message

        except Exception as e:
            logger.error("Error generating approval message", extra={
                "session_id": session.id,
                "error": str(e)
            })
            return f"Approval needed in session '{session.name}' (details unavailable)"

    async def format_session_list(self, sessions: list[Session]) -> str:
        """Format a list of sessions for display.

        Args:
            sessions: List of sessions to format

        Returns:
            Formatted session list
        """
        if not sessions:
            return "No sessions found"

        try:
            if hasattr(self.summarizer, 'format_session_list'):
                formatted = await self.summarizer.format_session_list(sessions)
            else:
                # Fallback implementation
                lines = ["📋 Sessions:"]
                for session in sessions[:10]:  # Limit to 10 sessions
                    status_emoji = {
                        "active": "🟢",
                        "paused": "⏸️",
                        "completed": "✅",
                        "error": "❌",
                        "idle": "⚪"
                    }.get(session.status.value, "❓")

                    line = f"{status_emoji} {session.name} ({session.status.value})"
                    lines.append(line)

                if len(sessions) > 10:
                    lines.append(f"... and {len(sessions) - 10} more")

                formatted = "\n".join(lines)

            logger.debug("Formatted session list", extra={
                "sessions_count": len(sessions)
            })
            return formatted

        except Exception as e:
            logger.error("Error formatting session list", extra={
                "sessions_count": len(sessions),
                "error": str(e)
            })
            return f"Error formatting session list: {str(e)}"

    async def get_summarizer_info(self) -> dict[str, Any]:
        """Get information about the current summarizer.

        Returns:
            Dictionary with summarizer information
        """
        summarizer_info = {
            "type": settings.SUMMARIZER_TYPE,
            "class": self.summarizer.__class__.__name__ if self.summarizer else None,
            "capabilities": []
        }

        # Check for optional methods
        if hasattr(self.summarizer, 'generate_status_message'):
            summarizer_info["capabilities"].append("status_messages")
        if hasattr(self.summarizer, 'generate_completion_message'):
            summarizer_info["capabilities"].append("completion_messages")
        if hasattr(self.summarizer, 'generate_error_message'):
            summarizer_info["capabilities"].append("error_messages")
        if hasattr(self.summarizer, 'generate_approval_message'):
            summarizer_info["capabilities"].append("approval_messages")
        if hasattr(self.summarizer, 'format_session_list'):
            summarizer_info["capabilities"].append("session_list_formatting")

        return summarizer_info