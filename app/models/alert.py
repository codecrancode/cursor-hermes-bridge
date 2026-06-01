"""Alert data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AlertType(Enum):
    """Alert type enumeration."""

    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    APPROVAL_NEEDED = "approval_needed"
    INACTIVITY_TIMEOUT = "inactivity_timeout"
    INFO = "info"
    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"


class AlertSeverity(Enum):
    """Alert severity enumeration."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alert data model representing a notification event."""

    id: str
    type: AlertType
    severity: AlertSeverity
    message: str
    session_id: str | None
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False

    @classmethod
    def create_new(
        cls,
        alert_type: AlertType | str,
        severity: AlertSeverity | str,
        message: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Create a new alert with generated ID and current timestamp."""
        if isinstance(alert_type, str):
            alert_type = AlertType(alert_type)
        if isinstance(severity, str):
            severity = AlertSeverity(severity)

        return Alert(
            id=str(uuid.uuid4()),
            type=alert_type,
            severity=severity,
            message=message,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
            acknowledged=False,
        )

    @classmethod
    def task_complete(
        cls, session_id: str, message: str | None = None
    ) -> Alert:
        """Create a task completion alert."""
        return cls.create_new(
            AlertType.TASK_COMPLETE,
            AlertSeverity.INFO,
            message or "Task completed successfully",
            session_id=session_id,
        )

    @classmethod
    def task_error(
        cls, session_id: str, error_message: str
    ) -> Alert:
        """Create a task error alert."""
        return cls.create_new(
            AlertType.TASK_ERROR,
            AlertSeverity.ERROR,
            f"Task failed: {error_message}",
            session_id=session_id,
        )

    @classmethod
    def approval_needed(
        cls, session_id: str, reason: str
    ) -> Alert:
        """Create an approval needed alert."""
        return cls.create_new(
            AlertType.APPROVAL_NEEDED,
            AlertSeverity.WARNING,
            f"Approval needed: {reason}",
            session_id=session_id,
        )

    @classmethod
    def inactivity_timeout(
        cls, session_id: str, minutes: int
    ) -> Alert:
        """Create an inactivity timeout alert."""
        return cls.create_new(
            AlertType.INACTIVITY_TIMEOUT,
            AlertSeverity.WARNING,
            f"Session inactive for {minutes} minutes",
            session_id=session_id,
        )

    @classmethod
    def info(cls, message: str, session_id: str | None = None) -> Alert:
        """Create an info alert."""
        return cls.create_new(
            AlertType.INFO,
            AlertSeverity.INFO,
            message,
            session_id=session_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "message": self.message,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Alert:
        """Create alert from dictionary."""
        return cls(
            id=data["id"],
            type=AlertType(data["type"]),
            severity=AlertSeverity(data["severity"]),
            message=data["message"],
            session_id=data.get("session_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            acknowledged=data.get("acknowledged", False),
        )

    def acknowledge(self) -> None:
        """Mark the alert as acknowledged."""
        self.acknowledged = True

    def is_critical(self) -> bool:
        """Check if the alert is critical severity."""
        return self.severity == AlertSeverity.CRITICAL

    def is_error(self) -> bool:
        """Check if the alert is error severity or higher."""
        return self.severity in {AlertSeverity.ERROR, AlertSeverity.CRITICAL}

    def requires_attention(self) -> bool:
        """Check if the alert requires immediate attention."""
        return self.type in {
            AlertType.TASK_ERROR,
            AlertType.APPROVAL_NEEDED,
        } or self.is_critical()