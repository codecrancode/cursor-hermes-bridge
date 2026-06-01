"""Filesystem watcher for monitoring Cursor log and session files."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..models.progress_event import ProgressEvent
from ..utils.config import settings
from ..utils.logging import get_logger

logger = get_logger("app.watchers.filesystem_watcher")


class CursorFileHandler(FileSystemEventHandler):
    """File system event handler for Cursor files."""

    def __init__(
        self,
        event_callback: Callable[[ProgressEvent], None],
        session_service: Any = None
    ) -> None:
        super().__init__()
        self.event_callback = event_callback
        self.session_service = session_service
        self._event_queue: asyncio.Queue[FileSystemEvent] = asyncio.Queue()
        self._processing_task: asyncio.Task | None = None

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if not event.is_directory:
            try:
                asyncio.create_task(self._queue_event(event, "modified"))
            except RuntimeError:
                # Event loop not running, queue for later
                pass

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if not event.is_directory:
            try:
                asyncio.create_task(self._queue_event(event, "created"))
            except RuntimeError:
                pass

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if not event.is_directory:
            try:
                asyncio.create_task(self._queue_event(event, "deleted"))
            except RuntimeError:
                pass

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move events."""
        if not event.is_directory:
            try:
                asyncio.create_task(self._queue_event(event, "moved"))
            except RuntimeError:
                pass

    async def _queue_event(self, event: FileSystemEvent, event_type: str) -> None:
        """Queue a file system event for processing."""
        # Add event type to the event object for processing
        setattr(event, 'event_type', event_type)
        await self._event_queue.put(event)

    async def start_processing(self) -> None:
        """Start processing queued events."""
        if self._processing_task and not self._processing_task.done():
            return

        self._processing_task = asyncio.create_task(self._process_events())

    async def stop_processing(self) -> None:
        """Stop processing events."""
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

    async def _process_events(self) -> None:
        """Process queued file system events."""
        while True:
            try:
                # Wait for events with timeout to allow cancellation
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error processing file system event", extra={"error": str(e)})

    async def _handle_event(self, event: FileSystemEvent) -> None:
        """Handle a file system event and generate progress events."""
        try:
            file_path = Path(event.src_path)
            event_type = getattr(event, 'event_type', 'unknown')

            # Determine session ID from file path
            session_id = self._extract_session_id(file_path)
            if not session_id:
                return

            # Generate appropriate progress event
            progress_event = await self._create_progress_event(
                session_id, file_path, event_type
            )

            if progress_event and self.event_callback:
                self.event_callback(progress_event)

        except Exception as e:
            logger.error("Error handling file system event", extra={
                "file_path": event.src_path,
                "error": str(e)
            })

    def _extract_session_id(self, file_path: Path) -> str | None:
        """Extract session ID from file path."""
        # Try different patterns to extract session ID
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

    async def _create_progress_event(
        self,
        session_id: str,
        file_path: Path,
        event_type: str
    ) -> ProgressEvent | None:
        """Create a progress event from file system event."""
        try:
            # Determine stage based on file type and event
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
                    "watcher": "filesystem"
                }
            )

        except Exception as e:
            logger.error("Error creating progress event", extra={
                "session_id": session_id,
                "file_path": str(file_path),
                "error": str(e)
            })
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


class FilesystemWatcher:
    """Filesystem watcher for monitoring Cursor files."""

    def __init__(
        self,
        event_callback: Callable[[ProgressEvent], None] | None = None,
        session_service: Any = None
    ) -> None:
        self.event_callback = event_callback
        self.session_service = session_service
        self.observer: Observer | None = None
        self.handlers: list[CursorFileHandler] = []
        self.watch_paths: list[str] = []
        self._running = False

    async def initialize(self) -> None:
        """Initialize the filesystem watcher."""
        logger.info("Initializing filesystem watcher")

        # Get paths to watch
        self.watch_paths = settings.get_cursor_log_paths()

        if not self.watch_paths:
            logger.warning("No valid watch paths found")
            return

        # Create observer
        self.observer = Observer()

        # Create handlers and set up watches
        for watch_path in self.watch_paths:
            path = Path(watch_path)
            if not path.exists():
                logger.warning("Watch path does not exist", extra={"path": watch_path})
                continue

            handler = CursorFileHandler(
                event_callback=self._handle_progress_event,
                session_service=self.session_service
            )
            self.handlers.append(handler)

            # Add watch (recursive for directories)
            self.observer.schedule(handler, watch_path, recursive=True)

            logger.info("Added filesystem watch", extra={"path": watch_path})

        logger.info("Filesystem watcher initialized", extra={
            "watch_paths": len(self.watch_paths),
            "handlers": len(self.handlers)
        })

    async def start(self) -> None:
        """Start the filesystem watcher."""
        if not self.observer or self._running:
            return

        logger.info("Starting filesystem watcher")

        # Start observer
        self.observer.start()

        # Start event processing for all handlers
        for handler in self.handlers:
            await handler.start_processing()

        self._running = True

    async def stop(self) -> None:
        """Stop the filesystem watcher."""
        if not self._running:
            return

        logger.info("Stopping filesystem watcher")

        # Stop event processing for all handlers
        for handler in self.handlers:
            await handler.stop_processing()

        # Stop observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5.0)

        self._running = False

    def _handle_progress_event(self, event: ProgressEvent) -> None:
        """Handle a progress event from file system changes."""
        logger.debug("Filesystem watcher generated progress event", extra={
            "session_id": event.session_id,
            "stage": event.stage,
            "detail": event.detail
        })

        # Forward to registered callback
        if self.event_callback:
            try:
                # If callback is async, run it in the event loop
                if asyncio.iscoroutinefunction(self.event_callback):
                    asyncio.create_task(self.event_callback(event))
                else:
                    self.event_callback(event)
            except Exception as e:
                logger.error("Error in progress event callback", extra={
                    "error": str(e),
                    "event_id": event.id
                })

    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._running and self.observer is not None and self.observer.is_alive()

    def get_watch_info(self) -> dict[str, Any]:
        """Get information about the filesystem watcher."""
        return {
            "running": self.is_running(),
            "watch_paths": self.watch_paths,
            "handler_count": len(self.handlers),
            "observer_alive": self.observer.is_alive() if self.observer else False,
            "watchdog_available": True  # If we got this far, watchdog is available
        }

    async def force_scan(self) -> list[ProgressEvent]:
        """Force a scan of all watch directories for recent changes.

        Returns:
            List of progress events generated from recent files
        """
        events = []

        try:
            # Scan each watch path for recent changes
            cutoff_time = datetime.utcnow().timestamp() - 300  # Last 5 minutes

            for watch_path in self.watch_paths:
                path = Path(watch_path)
                if not path.exists():
                    continue

                # Recursively scan for recent files
                for file_path in path.rglob('*'):
                    if not file_path.is_file():
                        continue

                    try:
                        stat = file_path.stat()
                        if stat.st_mtime > cutoff_time:
                            # Create a synthetic event for this recent file
                            handler = CursorFileHandler(
                                event_callback=lambda e: events.append(e)
                            )

                            # Determine event type based on age
                            if stat.st_ctime > cutoff_time:
                                event_type = 'created'
                            else:
                                event_type = 'modified'

                            session_id = handler._extract_session_id(file_path)
                            if session_id:
                                event = await handler._create_progress_event(
                                    session_id, file_path, event_type
                                )
                                if event:
                                    events.append(event)

                    except Exception as e:
                        logger.warning("Error scanning file", extra={
                            "file_path": str(file_path),
                            "error": str(e)
                        })

            logger.info("Force scan completed", extra={
                "watch_paths": len(self.watch_paths),
                "events_found": len(events)
            })

        except Exception as e:
            logger.error("Error during force scan", extra={"error": str(e)})

        return events