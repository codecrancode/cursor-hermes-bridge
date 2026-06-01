"""Local template-based summarizer."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from ..models.progress_event import ProgressEvent
from ..models.session import Session
from .base import BaseSummarizer


class LocalSummarizer(BaseSummarizer):
    """Template-based local summarizer that generates human-readable summaries."""

    def __init__(self) -> None:
        self.stage_emojis = {
            "session_started": "🚀",
            "session_ended": "🏁",
            "session_updated": "📝",
            "planning": "🧠",
            "editing": "✏️",
            "testing": "🧪",
            "completed": "✅",
            "error": "❌",
            "paused": "⏸️",
            "activity": "📝",
            "processing": "⚙️",
            "processing_complete": "✨",
            "starting": "🏁",
        }

        self.stage_descriptions = {
            "session_started": "Started session",
            "session_ended": "Ended session",
            "session_updated": "Updated session",
            "planning": "Planning and analysis",
            "editing": "Code editing",
            "testing": "Running tests",
            "completed": "Task completed",
            "error": "Error occurred",
            "paused": "Paused for approval",
            "activity": "General activity",
            "processing": "Processing files",
            "processing_complete": "Processing finished",
            "starting": "Starting work",
        }

    async def summarize_session(self, session: Session, events: list[ProgressEvent]) -> str:
        """Generate a comprehensive summary for a session."""
        if not events:
            return self._format_basic_session_info(session) + "\nNo progress events recorded."

        # Sort events by timestamp (most recent first)
        sorted_events = sorted(events, key=lambda e: e.timestamp, reverse=True)

        # Build summary sections
        sections = []

        # Session info
        sections.append(self._format_session_info(session, sorted_events))

        # Progress overview
        sections.append(self._format_progress_overview(sorted_events))

        # Recent activity (last 5 events)
        if len(sorted_events) > 0:
            sections.append(self._format_recent_activity(sorted_events[:5]))

        # Timeline summary
        if len(sorted_events) > 5:
            sections.append(self._format_timeline_summary(sorted_events))

        return "\n\n".join(sections)

    async def summarize_events(self, events: list[ProgressEvent]) -> str:
        """Generate a summary from a list of progress events."""
        if not events:
            return "No events to summarize."

        # Sort events by timestamp (most recent first)
        sorted_events = sorted(events, key=lambda e: e.timestamp, reverse=True)

        # Group events by stage
        stage_groups = {}
        for event in sorted_events:
            if event.stage not in stage_groups:
                stage_groups[event.stage] = []
            stage_groups[event.stage].append(event)

        # Build summary
        lines = []

        # Overview
        total_events = len(sorted_events)
        unique_stages = len(stage_groups)
        time_span = self._calculate_time_span(sorted_events)

        lines.append(f"📊 Summary: {total_events} events across {unique_stages} stages {time_span}")

        # Recent events (top 3)
        if sorted_events:
            lines.append("\n📋 Recent activity:")
            for event in sorted_events[:3]:
                emoji = self.stage_emojis.get(event.stage, "📝")
                time_ago = self._time_ago(event.timestamp)
                lines.append(f"  {emoji} {event.stage}: {event.detail} ({time_ago})")

        # Stage summary
        if len(stage_groups) > 1:
            lines.append(f"\n📈 Activity by stage:")
            stage_counts = Counter(event.stage for event in sorted_events)
            for stage, count in stage_counts.most_common(5):
                emoji = self.stage_emojis.get(stage, "📝")
                description = self.stage_descriptions.get(stage, stage)
                lines.append(f"  {emoji} {description}: {count} events")

        return "\n".join(lines)

    async def generate_status_message(
        self,
        session: Session | None,
        recent_events: list[ProgressEvent]
    ) -> str:
        """Generate a concise status message."""
        if not session:
            return "🔘 No active session"

        status_emoji = {
            "active": "🟢",
            "paused": "⏸️",
            "completed": "✅",
            "error": "❌",
            "idle": "⚪"
        }.get(session.status.value, "❓")

        message = f"{status_emoji} Session: {session.name} ({session.status.value})"

        if recent_events:
            latest_event = recent_events[0]
            stage_emoji = self.stage_emojis.get(latest_event.stage, "📝")
            time_ago = self._time_ago(latest_event.timestamp)
            message += f"\n{stage_emoji} Latest: {latest_event.detail} ({time_ago})"

            if len(recent_events) > 1:
                message += f"\n📊 {len(recent_events)} events in recent activity"
        else:
            message += "\n💤 No recent activity"

        return message

    async def generate_completion_message(
        self,
        session: Session,
        completion_event: ProgressEvent
    ) -> str:
        """Generate a completion notification message."""
        time_ago = self._time_ago(completion_event.timestamp)

        message = f"🎉 Task completed in session '{session.name}'"
        message += f"\n✅ {completion_event.detail}"
        message += f"\n🕐 Completed {time_ago}"

        return message

    async def generate_error_message(
        self,
        session: Session,
        error_event: ProgressEvent
    ) -> str:
        """Generate an error notification message."""
        time_ago = self._time_ago(error_event.timestamp)

        message = f"🚨 Error in session '{session.name}'"
        message += f"\n❌ Stage: {error_event.stage}"
        message += f"\n💥 Details: {error_event.detail}"
        message += f"\n🕐 Occurred {time_ago}"

        return message

    async def generate_approval_message(
        self,
        session: Session,
        approval_event: ProgressEvent
    ) -> str:
        """Generate an approval needed notification message."""
        time_ago = self._time_ago(approval_event.timestamp)

        message = f"⏸️ Approval needed in session '{session.name}'"
        message += f"\n🤔 Stage: {approval_event.stage}"
        message += f"\n📝 Details: {approval_event.detail}"
        message += f"\n🕐 Requested {time_ago}"
        message += f"\n💬 Please review and respond"

        return message

    async def format_session_list(self, sessions: list[Session]) -> str:
        """Format a list of sessions for display."""
        if not sessions:
            return "📭 No sessions found"

        # Sort sessions by update time (most recent first)
        sorted_sessions = sorted(sessions, key=lambda s: s.updated_at, reverse=True)

        lines = ["📋 Sessions:"]

        for i, session in enumerate(sorted_sessions[:10]):  # Limit to 10 sessions
            status_emoji = {
                "active": "🟢",
                "paused": "⏸️",
                "completed": "✅",
                "error": "❌",
                "idle": "⚪"
            }.get(session.status.value, "❓")

            time_ago = self._time_ago(session.updated_at)
            line = f"  {status_emoji} {session.name} ({session.status.value}) - {time_ago}"
            lines.append(line)

        if len(sorted_sessions) > 10:
            lines.append(f"  ... and {len(sorted_sessions) - 10} more sessions")

        return "\n".join(lines)

    def _format_basic_session_info(self, session: Session) -> str:
        """Format basic session information."""
        status_emoji = {
            "active": "🟢",
            "paused": "⏸️",
            "completed": "✅",
            "error": "❌",
            "idle": "⚪"
        }.get(session.status.value, "❓")

        created_ago = self._time_ago(session.created_at)
        updated_ago = self._time_ago(session.updated_at)

        return (
            f"{status_emoji} Session: {session.name}\n"
            f"📅 Created: {created_ago}\n"
            f"🔄 Updated: {updated_ago}\n"
            f"⚙️ Adapter: {session.adapter}"
        )

    def _format_session_info(self, session: Session, events: list[ProgressEvent]) -> str:
        """Format session information with event context."""
        basic_info = self._format_basic_session_info(session)

        if events:
            duration = self._calculate_session_duration(session, events)
            basic_info += f"\n⏱️ Duration: {duration}"

        return basic_info

    def _format_progress_overview(self, events: list[ProgressEvent]) -> str:
        """Format progress overview."""
        if not events:
            return ""

        stage_counts = Counter(event.stage for event in events)
        total_events = len(events)

        lines = [f"📊 Progress Overview ({total_events} events):"]

        # Show top stages
        for stage, count in stage_counts.most_common(5):
            emoji = self.stage_emojis.get(stage, "📝")
            description = self.stage_descriptions.get(stage, stage)
            percentage = (count / total_events) * 100
            lines.append(f"  {emoji} {description}: {count} ({percentage:.1f}%)")

        # Check for errors or completions
        error_count = sum(1 for e in events if e.has_error())
        completion_count = sum(1 for e in events if e.is_completion())

        if error_count > 0:
            lines.append(f"  ⚠️ Errors: {error_count}")
        if completion_count > 0:
            lines.append(f"  🎯 Completions: {completion_count}")

        return "\n".join(lines)

    def _format_recent_activity(self, recent_events: list[ProgressEvent]) -> str:
        """Format recent activity section."""
        if not recent_events:
            return ""

        lines = ["🕐 Recent Activity:"]

        for event in recent_events:
            emoji = self.stage_emojis.get(event.stage, "📝")
            time_ago = self._time_ago(event.timestamp)
            detail = event.detail[:60] + "..." if len(event.detail) > 60 else event.detail
            lines.append(f"  {emoji} {detail} ({time_ago})")

        return "\n".join(lines)

    def _format_timeline_summary(self, events: list[ProgressEvent]) -> str:
        """Format timeline summary for longer event lists."""
        if len(events) <= 5:
            return ""

        lines = ["📈 Timeline Summary:"]

        # Group events by hour
        hourly_activity = {}
        for event in events:
            hour_key = event.timestamp.replace(minute=0, second=0, microsecond=0)
            if hour_key not in hourly_activity:
                hourly_activity[hour_key] = 0
            hourly_activity[hour_key] += 1

        # Show most active periods
        sorted_hours = sorted(hourly_activity.items(), key=lambda x: x[1], reverse=True)

        for hour, count in sorted_hours[:3]:
            time_str = hour.strftime("%H:%M")
            lines.append(f"  📊 {time_str}: {count} events")

        return "\n".join(lines)

    def _time_ago(self, timestamp: datetime) -> str:
        """Format a timestamp as 'time ago' string."""
        now = datetime.utcnow()
        diff = now - timestamp

        if diff.total_seconds() < 60:
            return f"{int(diff.total_seconds())}s ago"
        elif diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() / 60)}m ago"
        elif diff.total_seconds() < 86400:
            return f"{int(diff.total_seconds() / 3600)}h ago"
        else:
            return f"{int(diff.total_seconds() / 86400)}d ago"

    def _calculate_time_span(self, events: list[ProgressEvent]) -> str:
        """Calculate and format the time span of events."""
        if not events:
            return ""

        timestamps = [event.timestamp for event in events]
        start_time = min(timestamps)
        end_time = max(timestamps)
        span = end_time - start_time

        if span.total_seconds() < 60:
            return f"(over {int(span.total_seconds())}s)"
        elif span.total_seconds() < 3600:
            return f"(over {int(span.total_seconds() / 60)}m)"
        elif span.total_seconds() < 86400:
            return f"(over {int(span.total_seconds() / 3600)}h)"
        else:
            return f"(over {int(span.total_seconds() / 86400)}d)"

    def _calculate_session_duration(self, session: Session, events: list[ProgressEvent]) -> str:
        """Calculate session duration."""
        if not events:
            duration = datetime.utcnow() - session.created_at
        else:
            latest_event = max(events, key=lambda e: e.timestamp)
            duration = latest_event.timestamp - session.created_at

        if duration.total_seconds() < 60:
            return f"{int(duration.total_seconds())} seconds"
        elif duration.total_seconds() < 3600:
            return f"{int(duration.total_seconds() / 60)} minutes"
        elif duration.total_seconds() < 86400:
            hours = int(duration.total_seconds() / 3600)
            minutes = int((duration.total_seconds() % 3600) / 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(duration.total_seconds() / 86400)
            hours = int((duration.total_seconds() % 86400) / 3600)
            return f"{days}d {hours}h"

    def get_capabilities(self) -> dict[str, bool]:
        """Get the capabilities of this summarizer."""
        return {
            "summarize_session": True,
            "summarize_events": True,
            "summarize_recent_activity": True,
            "generate_status_message": True,
            "generate_completion_message": True,
            "generate_error_message": True,
            "generate_approval_message": True,
            "format_session_list": True,
            "emoji_support": True,
            "time_formatting": True,
            "timeline_analysis": True,
        }

    def get_summarizer_info(self) -> dict[str, Any]:
        """Get information about this summarizer."""
        return {
            "name": "LocalSummarizer",
            "type": "template-based",
            "capabilities": self.get_capabilities(),
            "stage_emojis_count": len(self.stage_emojis),
            "stage_descriptions_count": len(self.stage_descriptions),
        }