"""Base summarizer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models.progress_event import ProgressEvent
from ..models.session import Session


class BaseSummarizer(ABC):
    """Abstract base class for summarizers."""

    @abstractmethod
    async def summarize_session(self, session: Session, events: list[ProgressEvent]) -> str:
        """Generate a summary for a session and its progress events.

        Args:
            session: The session to summarize
            events: Progress events for the session

        Returns:
            Human-readable summary string
        """

    @abstractmethod
    async def summarize_events(self, events: list[ProgressEvent]) -> str:
        """Generate a summary from a list of progress events.

        Args:
            events: Progress events to summarize

        Returns:
            Human-readable summary string
        """

    async def summarize_recent_activity(
        self,
        session: Session,
        events: list[ProgressEvent],
        minutes: int = 30
    ) -> str:
        """Generate a summary of recent activity for a session.

        Default implementation filters events by time and calls summarize_events.
        Subclasses can override for custom behavior.

        Args:
            session: The session to summarize
            events: Recent progress events (assumed to be pre-filtered)
            minutes: Number of minutes of recent activity covered

        Returns:
            Human-readable summary of recent activity
        """
        if not events:
            return f"No activity in the last {minutes} minutes"

        summary = await self.summarize_events(events)
        return f"Activity in the last {minutes} minutes:\n{summary}"

    # Optional methods that subclasses can implement for enhanced functionality

    async def generate_status_message(
        self,
        session: Session | None,
        recent_events: list[ProgressEvent]
    ) -> str:
        """Generate a concise status message suitable for notifications.

        Default implementation provides basic status.
        Subclasses should override for richer status messages.

        Args:
            session: Current session (None if no active session)
            recent_events: Recent progress events

        Returns:
            Concise status message
        """
        if not session:
            return "No active session"

        if not recent_events:
            return f"Session '{session.name}' ({session.status.value}) - No recent activity"

        latest_event = recent_events[0] if recent_events else None
        if latest_event:
            return (
                f"Session '{session.name}' ({session.status.value})\n"
                f"Latest: {latest_event.stage} - {latest_event.detail}"
            )
        else:
            return f"Session '{session.name}' ({session.status.value})"

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
        return f"✅ Task completed in session '{session.name}'\nDetails: {completion_event.detail}"

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
        return (
            f"❌ Error in session '{session.name}'\n"
            f"Stage: {error_event.stage}\n"
            f"Details: {error_event.detail}"
        )

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
        return (
            f"⏸️ Approval needed in session '{session.name}'\n"
            f"Stage: {approval_event.stage}\n"
            f"Details: {approval_event.detail}"
        )

    async def format_session_list(self, sessions: list[Session]) -> str:
        """Format a list of sessions for display.

        Args:
            sessions: List of sessions to format

        Returns:
            Formatted session list
        """
        if not sessions:
            return "No sessions found"

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

        return "\n".join(lines)

    def get_capabilities(self) -> dict[str, bool]:
        """Get the capabilities of this summarizer.

        Returns:
            Dictionary mapping capability names to support status
        """
        return {
            "summarize_session": True,
            "summarize_events": True,
            "summarize_recent_activity": True,
            "generate_status_message": True,
            "generate_completion_message": True,
            "generate_error_message": True,
            "generate_approval_message": True,
            "format_session_list": True,
        }

    def get_summarizer_info(self) -> dict[str, Any]:
        """Get information about this summarizer.

        Returns:
            Dictionary with summarizer information
        """
        return {
            "name": self.__class__.__name__,
            "capabilities": self.get_capabilities(),
        }