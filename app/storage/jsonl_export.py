"""JSONL export functionality for debugging and analysis."""

import json
import os
from datetime import datetime
from typing import Any, AsyncIterator

import aiofiles

from ..models.alert import Alert
from ..models.progress_event import ProgressEvent
from ..models.session import Session
from ..utils.logging import get_logger

logger = get_logger("app.storage.jsonl_export")


class JSONLExporter:
    """Exports database records to JSONL format for debugging and analysis."""

    def __init__(self, export_path: str) -> None:
        self.export_path = export_path
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the export directory exists."""
        directory = os.path.dirname(self.export_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def _format_record(
        self,
        record_type: str,
        data: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Format a record for JSONL export."""
        formatted = {
            "export_timestamp": (timestamp or datetime.utcnow()).isoformat(),
            "record_type": record_type,
            "data": data,
        }
        return formatted

    async def export_session(self, session: Session) -> None:
        """Export a single session to JSONL."""
        if not self.export_path:
            return

        record = self._format_record("session", session.to_dict())
        await self._write_record(record)

        logger.debug("Exported session to JSONL", extra={
            "session_id": session.id,
            "export_path": self.export_path
        })

    async def export_progress_event(self, event: ProgressEvent) -> None:
        """Export a single progress event to JSONL."""
        if not self.export_path:
            return

        record = self._format_record("progress_event", event.to_dict())
        await self._write_record(record)

        logger.debug("Exported progress event to JSONL", extra={
            "event_id": event.id,
            "session_id": event.session_id,
            "export_path": self.export_path
        })

    async def export_alert(self, alert: Alert) -> None:
        """Export a single alert to JSONL."""
        if not self.export_path:
            return

        record = self._format_record("alert", alert.to_dict())
        await self._write_record(record)

        logger.debug("Exported alert to JSONL", extra={
            "alert_id": alert.id,
            "alert_type": alert.type.value,
            "export_path": self.export_path
        })

    async def export_sessions_batch(self, sessions: list[Session]) -> int:
        """Export multiple sessions to JSONL."""
        if not self.export_path or not sessions:
            return 0

        records = []
        for session in sessions:
            record = self._format_record("session", session.to_dict())
            records.append(record)

        await self._write_records(records)

        logger.info("Exported sessions batch to JSONL", extra={
            "count": len(sessions),
            "export_path": self.export_path
        })
        return len(sessions)

    async def export_progress_events_batch(self, events: list[ProgressEvent]) -> int:
        """Export multiple progress events to JSONL."""
        if not self.export_path or not events:
            return 0

        records = []
        for event in events:
            record = self._format_record("progress_event", event.to_dict())
            records.append(record)

        await self._write_records(records)

        logger.info("Exported progress events batch to JSONL", extra={
            "count": len(events),
            "export_path": self.export_path
        })
        return len(events)

    async def export_alerts_batch(self, alerts: list[Alert]) -> int:
        """Export multiple alerts to JSONL."""
        if not self.export_path or not alerts:
            return 0

        records = []
        for alert in alerts:
            record = self._format_record("alert", alert.to_dict())
            records.append(record)

        await self._write_records(records)

        logger.info("Exported alerts batch to JSONL", extra={
            "count": len(alerts),
            "export_path": self.export_path
        })
        return len(alerts)

    async def _write_record(self, record: dict[str, Any]) -> None:
        """Write a single record to the JSONL file."""
        try:
            async with aiofiles.open(self.export_path, "a", encoding="utf-8") as f:
                await f.write(json.dumps(record, separators=(",", ":")) + "\n")
        except Exception as e:
            logger.error("Failed to write JSONL record", extra={
                "export_path": self.export_path,
                "error": str(e)
            })

    async def _write_records(self, records: list[dict[str, Any]]) -> None:
        """Write multiple records to the JSONL file."""
        if not records:
            return

        try:
            async with aiofiles.open(self.export_path, "a", encoding="utf-8") as f:
                for record in records:
                    await f.write(json.dumps(record, separators=(",", ":")) + "\n")
        except Exception as e:
            logger.error("Failed to write JSONL records", extra={
                "export_path": self.export_path,
                "count": len(records),
                "error": str(e)
            })

    async def read_records(
        self,
        record_type: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Read records from the JSONL file."""
        if not os.path.exists(self.export_path):
            return

        count = 0
        try:
            async with aiofiles.open(self.export_path, "r", encoding="utf-8") as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)

                        # Filter by record type if specified
                        if record_type and record.get("record_type") != record_type:
                            continue

                        yield record
                        count += 1

                        # Stop if we've reached the limit
                        if limit and count >= limit:
                            break

                    except json.JSONDecodeError as e:
                        logger.warning("Failed to parse JSONL line", extra={
                            "line": line[:100],  # First 100 chars
                            "error": str(e)
                        })
                        continue

        except Exception as e:
            logger.error("Failed to read JSONL file", extra={
                "export_path": self.export_path,
                "error": str(e)
            })

    async def get_export_stats(self) -> dict[str, Any]:
        """Get statistics about the export file."""
        if not os.path.exists(self.export_path):
            return {
                "exists": False,
                "size_bytes": 0,
                "record_counts": {},
                "file_modified": None,
            }

        # Get file stats
        stat = os.stat(self.export_path)
        file_size = stat.st_size
        file_modified = datetime.fromtimestamp(stat.st_mtime)

        # Count records by type
        record_counts: dict[str, int] = {}
        total_records = 0

        try:
            async for record in self.read_records():
                record_type = record.get("record_type", "unknown")
                record_counts[record_type] = record_counts.get(record_type, 0) + 1
                total_records += 1
        except Exception as e:
            logger.error("Failed to count JSONL records", extra={
                "export_path": self.export_path,
                "error": str(e)
            })

        return {
            "exists": True,
            "size_bytes": file_size,
            "total_records": total_records,
            "record_counts": record_counts,
            "file_modified": file_modified.isoformat(),
        }

    async def rotate_export_file(self, max_size_mb: float = 100.0) -> bool:
        """Rotate the export file if it exceeds the maximum size."""
        if not os.path.exists(self.export_path):
            return False

        file_size_mb = os.path.getsize(self.export_path) / (1024 * 1024)
        if file_size_mb <= max_size_mb:
            return False

        # Create rotated filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        rotated_path = f"{self.export_path}.{timestamp}"

        try:
            os.rename(self.export_path, rotated_path)
            logger.info("Rotated JSONL export file", extra={
                "original_path": self.export_path,
                "rotated_path": rotated_path,
                "size_mb": file_size_mb
            })
            return True
        except Exception as e:
            logger.error("Failed to rotate JSONL export file", extra={
                "export_path": self.export_path,
                "error": str(e)
            })
            return False

    async def cleanup_old_exports(self, days: int = 30) -> int:
        """Clean up old rotated export files."""
        if not self.export_path:
            return 0

        export_dir = os.path.dirname(self.export_path)
        export_name = os.path.basename(self.export_path)

        if not os.path.exists(export_dir):
            return 0

        cutoff_timestamp = datetime.utcnow().timestamp() - (days * 24 * 3600)
        removed_count = 0

        try:
            for filename in os.listdir(export_dir):
                if not filename.startswith(export_name + "."):
                    continue

                file_path = os.path.join(export_dir, filename)
                file_stat = os.stat(file_path)

                if file_stat.st_mtime < cutoff_timestamp:
                    os.remove(file_path)
                    removed_count += 1
                    logger.debug("Removed old export file", extra={
                        "file_path": file_path,
                        "age_days": (datetime.utcnow().timestamp() - file_stat.st_mtime) / (24 * 3600)
                    })

        except Exception as e:
            logger.error("Failed to cleanup old export files", extra={
                "export_dir": export_dir,
                "error": str(e)
            })

        if removed_count > 0:
            logger.info("Cleaned up old export files", extra={
                "removed_count": removed_count,
                "cutoff_days": days
            })

        return removed_count