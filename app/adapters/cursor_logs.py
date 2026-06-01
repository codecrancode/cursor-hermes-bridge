"""Cursor logs adapter - monitors Cursor through log and session files."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..models.command_request import CommandType
from ..models.command_result import CommandResult
from ..models.progress_event import ProgressEvent
from ..models.session import Session, SessionStatus
from ..utils.config import settings
from ..utils.logging import get_logger
from .base import (
    AdapterUnavailableError,
    CommunicationError,
    CursorAdapter,
    SessionNotFoundError,
)

logger = get_logger("app.adapters.cursor_logs")


class CursorLogsAdapter(CursorAdapter):
    """Adapter that monitors Cursor through its log and session files."""

    def __init__(self) -> None:
        self._log_dir = Path(settings.CURSOR_LOG_DIR).expanduser()
        self._session_dir = Path(settings.CURSOR_SESSION_DIR).expanduser()
        self._sessions_cache: dict[str, Session] = {}
        self._last_scan = datetime.utcnow()
        self._scan_interval = 10  # seconds
        self._initialized = False

    @property
    def name(self) -> str:
        return "cursor_logs"

    @property
    def description(self) -> str:
        return "Monitors Cursor through log and session files (read-only fallback)"

    async def initialize(self) -> None:
        """Initialize the adapter and scan for existing sessions."""
        if self._initialized:
            return

        logger.info("Initializing cursor logs adapter", extra={
            "log_dir": str(self._log_dir),
            "session_dir": str(self._session_dir)
        })

        await self._scan_sessions()
        self._initialized = True

    async def cleanup(self) -> None:
        """Clean up adapter resources."""
        self._sessions_cache.clear()
        self._initialized = False
        logger.info("Cleaned up cursor logs adapter")

    def is_available(self) -> bool:
        """Check if Cursor directories are accessible."""
        return (
            self._log_dir.exists() and self._log_dir.is_dir() and
            self._session_dir.exists() and self._session_dir.is_dir()
        )

    def get_capabilities(self) -> dict[str, bool]:
        """Get adapter capabilities."""
        capabilities = super().get_capabilities()
        capabilities.update({
            "send_prompt": False,  # Read-only adapter
            "continue_session": False,
            "stop_session": False,
            "new_session": False,
            "switch_session": False,
            "real_time_monitoring": True,
            "bidirectional_communication": False,
            "file_operations": False,
        })
        return capabilities

    async def get_status(self) -> dict[str, Any]:
        """Get current Cursor status from log files."""
        if not self.is_available():
            raise AdapterUnavailableError("Cursor directories not accessible", self.name)

        await self._refresh_if_needed()

        # Find the most recently active session
        active_session = None
        last_activity = None

        for session in self._sessions_cache.values():
            if session.status == SessionStatus.ACTIVE:
                active_session = session
                break
            elif (
                last_activity is None or
                session.updated_at > last_activity
            ):
                last_activity = session.updated_at
                if session.status in {SessionStatus.ACTIVE, SessionStatus.PAUSED}:
                    active_session = session

        # Get workspace info
        workspace_info = await self._get_workspace_from_logs()

        return {
            "is_running": self._is_cursor_running(),
            "current_session": active_session.id if active_session else None,
            "session_count": len(self._sessions_cache),
            "last_activity": last_activity.isoformat() if last_activity else None,
            "workspace": workspace_info.get("path"),
            "adapter": self.name,
        }

    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult:
        """Send prompt - not supported in read-only adapter."""
        return CommandResult.create_error(
            request_id="",
            command=CommandType.SEND,
            error="Send prompt not supported by logs adapter (read-only)",
            session_id=session_id
        )

    async def continue_session(self, session_id: str) -> CommandResult:
        """Continue session - not supported in read-only adapter."""
        return CommandResult.create_error(
            request_id="",
            command=CommandType.CONTINUE,
            error="Continue session not supported by logs adapter (read-only)",
            session_id=session_id
        )

    async def stop_session(self, session_id: str) -> CommandResult:
        """Stop session - not supported in read-only adapter."""
        return CommandResult.create_error(
            request_id="",
            command=CommandType.STOP,
            error="Stop session not supported by logs adapter (read-only)",
            session_id=session_id
        )

    async def new_session(self, name: str | None = None) -> CommandResult:
        """Create new session - not supported in read-only adapter."""
        return CommandResult.create_error(
            request_id="",
            command=CommandType.NEW,
            error="New session not supported by logs adapter (read-only)"
        )

    async def list_sessions(self) -> list[Session]:
        """List all discovered sessions."""
        await self._refresh_if_needed()
        return list(self._sessions_cache.values())

    async def switch_session(self, session_id: str) -> CommandResult:
        """Switch session - not supported in read-only adapter."""
        return CommandResult.create_error(
            request_id="",
            command=CommandType.SWITCH,
            error="Switch session not supported by logs adapter (read-only)",
            session_id=session_id
        )

    async def get_session_summary(self, session_id: str) -> str:
        """Get session summary from log files."""
        await self._refresh_if_needed()

        session = self._sessions_cache.get(session_id)
        if not session:
            return f"Session {session_id} not found"

        # Try to read session-specific logs
        session_log = await self._read_session_log(session_id)
        progress_events = await self.get_progress(session_id)

        # Build summary
        summary_parts = [
            f"Session: {session.name}",
            f"Status: {session.status.value}",
            f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Updated: {session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if progress_events:
            summary_parts.append(f"Progress events: {len(progress_events)}")
            recent_events = progress_events[:3]
            summary_parts.append("Recent activity:")
            for event in recent_events:
                summary_parts.append(f"  - {event.stage}: {event.detail}")

        if session_log:
            summary_parts.append(f"Log size: {len(session_log)} characters")

        return "\n".join(summary_parts)

    async def tail_session(self, session_id: str, lines: int = 20) -> str:
        """Get last N lines from session log."""
        session_log = await self._read_session_log(session_id)
        if not session_log:
            return f"No log data found for session {session_id}"

        log_lines = session_log.split("\n")
        tail_lines = log_lines[-lines:] if len(log_lines) >= lines else log_lines
        return "\n".join(tail_lines)

    async def get_progress(self, session_id: str) -> list[ProgressEvent]:
        """Extract progress events from session logs."""
        session_log = await self._read_session_log(session_id)
        if not session_log:
            return []

        events = []

        # Parse log entries for progress indicators
        log_lines = session_log.split("\n")
        for i, line in enumerate(log_lines):
            event = self._parse_log_line_for_progress(session_id, line, i)
            if event:
                events.append(event)

        # Sort by timestamp (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    async def get_workspace_info(self) -> dict[str, Any]:
        """Get workspace information from logs."""
        return await self._get_workspace_from_logs()

    # Helper methods

    async def _refresh_if_needed(self) -> None:
        """Refresh session cache if enough time has passed."""
        now = datetime.utcnow()
        if (now - self._last_scan).total_seconds() >= self._scan_interval:
            await self._scan_sessions()

    async def _scan_sessions(self) -> None:
        """Scan for sessions in the session directory."""
        if not self._session_dir.exists():
            logger.warning("Session directory does not exist", extra={
                "session_dir": str(self._session_dir)
            })
            return

        try:
            # Look for session files (JSON files in sessions directory)
            session_files = list(self._session_dir.glob("*.json"))

            # Update cache
            current_session_ids = set()

            for session_file in session_files:
                try:
                    session = await self._parse_session_file(session_file)
                    if session:
                        self._sessions_cache[session.id] = session
                        current_session_ids.add(session.id)
                except Exception as e:
                    logger.warning("Failed to parse session file", extra={
                        "file": str(session_file),
                        "error": str(e)
                    })

            # Remove sessions that no longer exist
            for session_id in list(self._sessions_cache.keys()):
                if session_id not in current_session_ids:
                    del self._sessions_cache[session_id]

            self._last_scan = datetime.utcnow()
            logger.debug("Scanned sessions", extra={
                "session_count": len(current_session_ids),
                "files_processed": len(session_files)
            })

        except Exception as e:
            logger.error("Failed to scan sessions", extra={
                "session_dir": str(self._session_dir),
                "error": str(e)
            })

    async def _parse_session_file(self, session_file: Path) -> Session | None:
        """Parse a session file to extract session information."""
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extract session information from the file structure
            # This is a best-guess implementation since we don't have the exact
            # Cursor session file format
            session_id = session_file.stem
            name = data.get("name", session_id)

            # Try to determine status from file modification time and content
            file_stat = session_file.stat()
            modified_time = datetime.fromtimestamp(file_stat.st_mtime)

            # Consider session active if modified recently (within 5 minutes)
            is_recent = (datetime.utcnow() - modified_time) < timedelta(minutes=5)
            status = SessionStatus.ACTIVE if is_recent else SessionStatus.IDLE

            # Look for status indicators in the data
            if "status" in data:
                try:
                    status = SessionStatus(data["status"])
                except ValueError:
                    pass

            return Session(
                id=session_id,
                name=name,
                status=status,
                adapter=self.name,
                created_at=modified_time,  # Use file time as created time
                updated_at=modified_time,
                metadata={
                    "file_path": str(session_file),
                    "file_size": file_stat.st_size,
                    "original_data": data,
                }
            )

        except Exception as e:
            logger.error("Failed to parse session file", extra={
                "file": str(session_file),
                "error": str(e)
            })
            return None

    async def _read_session_log(self, session_id: str) -> str:
        """Read log content for a specific session."""
        # Look for session-specific log files
        possible_log_paths = [
            self._log_dir / f"{session_id}.log",
            self._log_dir / f"session_{session_id}.log",
            self._log_dir / "main.log",  # Fall back to main log
        ]

        for log_path in possible_log_paths:
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    logger.debug("Read session log", extra={
                        "session_id": session_id,
                        "log_path": str(log_path),
                        "size": len(content)
                    })
                    return content
                except Exception as e:
                    logger.warning("Failed to read log file", extra={
                        "log_path": str(log_path),
                        "error": str(e)
                    })

        # If no specific session log, try to extract session content from main log
        return await self._extract_session_from_main_log(session_id)

    async def _extract_session_from_main_log(self, session_id: str) -> str:
        """Extract session-related entries from the main log."""
        main_log = self._log_dir / "main.log"
        if not main_log.exists():
            return ""

        try:
            with open(main_log, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract lines that mention the session ID
            lines = content.split("\n")
            session_lines = [
                line for line in lines
                if session_id in line
            ]

            return "\n".join(session_lines)

        except Exception as e:
            logger.warning("Failed to extract from main log", extra={
                "session_id": session_id,
                "error": str(e)
            })
            return ""

    def _parse_log_line_for_progress(
        self,
        session_id: str,
        line: str,
        line_number: int
    ) -> ProgressEvent | None:
        """Parse a log line for progress information."""
        # Skip empty lines
        if not line.strip():
            return None

        # Common progress patterns to look for
        patterns = [
            (r"(?i)starting|begin|init", "starting"),
            (r"(?i)planning|analyze|thinking", "planning"),
            (r"(?i)writing|editing|modifying", "editing"),
            (r"(?i)testing|running tests", "testing"),
            (r"(?i)completed?|finished|done", "completed"),
            (r"(?i)error|failed|exception", "error"),
            (r"(?i)waiting|paused|approval", "paused"),
        ]

        for pattern, stage in patterns:
            if re.search(pattern, line):
                # Extract timestamp if present
                timestamp_match = re.search(
                    r"(\d{4}-\d{2}-\d{2}[\s\T]\d{2}:\d{2}:\d{2})",
                    line
                )
                if timestamp_match:
                    try:
                        timestamp = datetime.fromisoformat(
                            timestamp_match.group(1).replace("T", " ")
                        )
                    except ValueError:
                        timestamp = datetime.utcnow()
                else:
                    timestamp = datetime.utcnow()

                return ProgressEvent.create_new(
                    session_id=session_id,
                    stage=stage,
                    detail=line.strip(),
                    metadata={
                        "line_number": line_number,
                        "adapter": self.name,
                    }
                )

        return None

    async def _get_workspace_from_logs(self) -> dict[str, Any]:
        """Extract workspace information from logs."""
        workspace_info: dict[str, Any] = {
            "path": None,
            "name": None,
            "files_count": None,
            "git_status": None,
        }

        # Try to read workspace info from various log files
        possible_logs = [
            self._log_dir / "main.log",
            self._log_dir / "workspace.log",
            self._log_dir / "renderer.log",
        ]

        for log_path in possible_logs:
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Look for workspace path patterns
                    path_patterns = [
                        r"workspace[:\s]+['\"]([^'\"]+)['\"]",
                        r"opened folder[:\s]+['\"]([^'\"]+)['\"]",
                        r"working directory[:\s]+['\"]([^'\"]+)['\"]",
                    ]

                    for pattern in path_patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            workspace_path = match.group(1)
                            workspace_info["path"] = workspace_path
                            workspace_info["name"] = os.path.basename(workspace_path)
                            break

                    if workspace_info["path"]:
                        break

                except Exception as e:
                    logger.debug("Failed to read workspace log", extra={
                        "log_path": str(log_path),
                        "error": str(e)
                    })

        return workspace_info

    def _is_cursor_running(self) -> bool:
        """Check if Cursor appears to be running by looking for recent activity."""
        # Check if any log files have been modified recently (within 2 minutes)
        cutoff = datetime.utcnow() - timedelta(minutes=2)

        for log_file in self._log_dir.glob("*.log"):
            try:
                stat = log_file.stat()
                modified = datetime.fromtimestamp(stat.st_mtime)
                if modified > cutoff:
                    return True
            except Exception:
                continue

        return False

    async def validate_session_id(self, session_id: str) -> bool:
        """Validate that a session ID exists."""
        await self._refresh_if_needed()
        return session_id in self._sessions_cache