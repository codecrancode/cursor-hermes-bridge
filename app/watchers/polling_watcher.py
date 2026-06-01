"""Polling-based watcher for monitoring Cursor files when filesystem watching is not available."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from ..models.progress_event import ProgressEvent
from ..utils.config import settings
from ..utils.logging import get_logger

logger = get_logger("app.watchers.polling_watcher")


class PollingWatcher:
    """Polling-based file watcher as fallback for filesystem watching."""

    def __init__(
        self,
        event_callback: Callable[[ProgressEvent], None] | None = None,
        session_service: Any = None,
        poll_interval: float = 5.0
    ) -> None:
        self.event_callback = event_callback
        self.session_service = session_service
        self.poll_interval = poll_interval
        self.watch_paths: list[str] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._file_states: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Initialize the polling watcher."""
        logger.info("Initializing polling watcher")

        # Get paths to watch
        self.watch_paths = settings.get_cursor_log_paths()

        if not self.watch_paths:
            logger.warning("No valid watch paths found")
            return

        # Initialize file states
        await self._scan_initial_state()

        logger.info("Polling watcher initialized", extra={
            "watch_paths": len(self.watch_paths),
            "poll_interval": self.poll_interval,
            "tracked_files": len(self._file_states)
        })

    async def start(self) -> None:
        """Start the polling watcher."""
        if self._running or not self.watch_paths:
            return

        logger.info("Starting polling watcher")
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the polling watcher."""
        if not self._running:
            return

        logger.info("Stopping polling watcher")
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_files()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in polling loop", extra={"error": str(e)})
                await asyncio.sleep(self.poll_interval)

    async def _poll_files(self) -> None:
        """Poll files for changes."""
        try:
            new_events = []

            for watch_path in self.watch_paths:
                path = Path(watch_path)
                if not path.exists():
                    continue

                # Recursively scan for files
                for file_path in path.rglob('*'):
                    if not file_path.is_file():
                        continue

                    file_key = str(file_path)
                    current_state = await self._get_file_state(file_path)

                    if file_key in self._file_states:
                        # Check for changes
                        old_state = self._file_states[file_key]
                        events = self._detect_changes(file_path, old_state, current_state)
                        new_events.extend(events)

                        # Update state
                        self._file_states[file_key] = current_state
                    else:
                        # New file
                        self._file_states[file_key] = current_state
                        event = await self._create_file_event(file_path, 'created')
                        if event:
                            new_events.append(event)

            # Check for deleted files
            current_files = set()
            for watch_path in self.watch_paths:
                path = Path(watch_path)
                if path.exists():
                    current_files.update(str(p) for p in path.rglob('*') if p.is_file())

            deleted_files = set(self._file_states.keys()) - current_files
            for deleted_file in deleted_files:
                file_path = Path(deleted_file)
                event = await self._create_file_event(file_path, 'deleted')
                if event:
                    new_events.append(event)
                del self._file_states[deleted_file]

            # Process new events
            for event in new_events:
                await self._handle_progress_event(event)

        except Exception as e:
            logger.error("Error polling files", extra={"error": str(e)})

    async def _scan_initial_state(self) -> None:
        """Scan initial state of all files."""
        try:
            for watch_path in self.watch_paths:
                path = Path(watch_path)
                if not path.exists():
                    continue

                for file_path in path.rglob('*'):
                    if file_path.is_file():
                        file_key = str(file_path)
                        self._file_states[file_key] = await self._get_file_state(file_path)

        except Exception as e:
            logger.error("Error scanning initial state", extra={"error": str(e)})

    async def _get_file_state(self, file_path: Path) -> dict[str, Any]:
        """Get the current state of a file."""
        try:
            if not file_path.exists():
                return {"exists": False}

            stat = file_path.stat()
            return {
                "exists": True,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "ctime": stat.st_ctime,
            }

        except Exception as e:
            logger.debug("Error getting file state", extra={
                "file_path": str(file_path),
                "error": str(e)
            })
            return {"exists": False, "error": str(e)}

    def _detect_changes(
        self,
        file_path: Path,
        old_state: dict[str, Any],
        new_state: dict[str, Any]
    ) -> list[ProgressEvent]:
        """Detect changes between old and new file states."""
        events = []

        # File was deleted
        if old_state.get("exists") and not new_state.get("exists"):
            return []  # Handled separately in main loop

        # File was created
        if not old_state.get("exists") and new_state.get("exists"):
            return []  # Handled separately in main loop

        # File was modified
        if (
            old_state.get("exists") and new_state.get("exists") and
            (old_state.get("size") != new_state.get("size") or
             old_state.get("mtime") != new_state.get("mtime"))
        ):
            asyncio.create_task(self._create_file_event_async(file_path, 'modified', events))

        return events

    async def _create_file_event_async(self, file_path: Path, event_type: str, events: list) -> None:
        """Async wrapper for creating file events."""
        event = await self._create_file_event(file_path, event_type)
        if event:
            events.append(event)

    async def _create_file_event(self, file_path: Path, event_type: str) -> ProgressEvent | None:
        """Create a progress event for a file change."""
        try:
            # Extract session ID from file path
            session_id = self._extract_session_id(file_path)
            if not session_id:
                return None

            # Determine stage
            stage = self._determine_stage(file_path, event_type)
            if not stage:
                return None

            # Create detail message
            detail = f"File {event_type}: {file_path.name}"

            # Add file size if available
            if event_type in ['created', 'modified'] and file_path.exists():
                try:
                    size = file_path.stat().st_size
                    detail += f" ({size} bytes)"
                except Exception:
                    pass

            # Create progress event
            return ProgressEvent.create_new(
                session_id=session_id,
                stage=stage,
                detail=detail,
                metadata={
                    "file_path": str(file_path),
                    "event_type": event_type,
                    "file_name": file_path.name,
                    "file_extension": file_path.suffix,
                    "watcher": "polling"
                }
            )

        except Exception as e:
            logger.error("Error creating file event", extra={
                "file_path": str(file_path),
                "event_type": event_type,
                "error": str(e)
            })
            return None

    def _extract_session_id(self, file_path: Path) -> str | None:
        """Extract session ID from file path."""
        # Use similar logic to filesystem watcher
        stem = file_path.stem

        # Pattern 1: filename contains session ID directly
        if len(stem) >= 8 and '-' in stem:
            parts = stem.split('-')
            if len(parts) >= 2:
                return parts[0]  # Assume first part is session ID

        # Pattern 2: use parent directory name if it looks like a session ID
        parent = file_path.parent.name
        if len(parent) >= 8 and '-' in parent:
            return parent

        # Pattern 3: use filename as session ID if it's long enough
        if len(stem) >= 8:
            return stem

        # Pattern 4: for generic log files, use "main" as session ID
        if file_path.name in ['main.log', 'renderer.log', 'shared-process.log']:
            return "main"

        return None

    def _determine_stage(self, file_path: Path, event_type: str) -> str | None:
        """Determine the progress stage from file characteristics."""
        file_name = file_path.name.lower()
        file_ext = file_path.suffix.lower()

        # Log files indicate activity
        if file_ext == '.log' or 'log' in file_name:
            if event_type == 'created':
                return 'session_started'
            elif event_type == 'modified':
                return 'activity'
            elif event_type == 'deleted':
                return 'session_ended'

        # Session files
        if file_ext in ['.json', '.session']:
            if event_type == 'created':
                return 'session_started'
            elif event_type == 'modified':
                return 'session_updated'
            elif event_type == 'deleted':
                return 'session_ended'

        # Temporary files might indicate processing
        if file_name.startswith('tmp') or file_name.startswith('temp'):
            if event_type == 'created':
                return 'processing'
            elif event_type == 'deleted':
                return 'processing_complete'

        # Error files
        if 'error' in file_name or 'crash' in file_name:
            return 'error'

        # Default to generic activity
        if event_type in ['created', 'modified']:
            return 'activity'

        return None

    async def _handle_progress_event(self, event: ProgressEvent) -> None:
        """Handle a progress event from polling changes."""
        logger.debug("Polling watcher generated progress event", extra={
            "session_id": event.session_id,
            "stage": event.stage,
            "detail": event.detail
        })

        # Forward to registered callback
        if self.event_callback:
            try:
                # If callback is async, await it
                if asyncio.iscoroutinefunction(self.event_callback):
                    await self.event_callback(event)
                else:
                    self.event_callback(event)
            except Exception as e:
                logger.error("Error in progress event callback", extra={
                    "error": str(e),
                    "event_id": event.id
                })

    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._running and (self._task is None or not self._task.done())

    def get_watch_info(self) -> dict[str, Any]:
        """Get information about the polling watcher."""
        return {
            "running": self.is_running(),
            "watch_paths": self.watch_paths,
            "poll_interval": self.poll_interval,
            "tracked_files": len(self._file_states),
            "watchdog_available": False  # This is the fallback watcher
        }

    async def force_scan(self) -> list[ProgressEvent]:
        """Force a scan for changes and return generated events.

        Returns:
            List of progress events generated from recent changes
        """
        events = []

        try:
            # Temporarily capture events during scan
            original_callback = self.event_callback
            captured_events = []

            def capture_event(event: ProgressEvent) -> None:
                captured_events.append(event)

            self.event_callback = capture_event

            # Run a poll cycle
            await self._poll_files()

            # Restore original callback
            self.event_callback = original_callback

            # Return captured events
            events = captured_events

            logger.info("Force scan completed", extra={
                "watch_paths": len(self.watch_paths),
                "events_found": len(events)
            })

        except Exception as e:
            logger.error("Error during force scan", extra={"error": str(e)})

        return events

    async def adjust_poll_interval(self, new_interval: float) -> None:
        """Adjust the polling interval.

        Args:
            new_interval: New interval in seconds
        """
        if new_interval <= 0:
            raise ValueError("Poll interval must be positive")

        old_interval = self.poll_interval
        self.poll_interval = new_interval

        logger.info("Adjusted poll interval", extra={
            "old_interval": old_interval,
            "new_interval": new_interval
        })

    async def get_file_statistics(self) -> dict[str, Any]:
        """Get statistics about tracked files.

        Returns:
            Dictionary with file statistics
        """
        stats = {
            "tracked_files": len(self._file_states),
            "by_extension": {},
            "by_directory": {},
            "total_size": 0,
            "recent_modifications": 0
        }

        cutoff_time = datetime.utcnow().timestamp() - 300  # Last 5 minutes

        try:
            for file_path, state in self._file_states.items():
                if not state.get("exists", False):
                    continue

                path = Path(file_path)

                # Count by extension
                ext = path.suffix.lower() or "no_extension"
                stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1

                # Count by directory
                parent = str(path.parent)
                stats["by_directory"][parent] = stats["by_directory"].get(parent, 0) + 1

                # Add to total size
                stats["total_size"] += state.get("size", 0)

                # Count recent modifications
                if state.get("mtime", 0) > cutoff_time:
                    stats["recent_modifications"] += 1

        except Exception as e:
            logger.error("Error calculating file statistics", extra={"error": str(e)})

        return stats