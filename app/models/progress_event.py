"""Progress event data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProgressEvent:
    """Progress event data model representing a step in a session's progress."""

    id: str
    session_id: str
    stage: str
    detail: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_new(
        self,
        session_id: str,
        stage: str,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProgressEvent:
        """Create a new progress event with generated ID and current timestamp."""
        return ProgressEvent(
            id=str(uuid.uuid4()),
            session_id=session_id,
            stage=stage,
            detail=detail,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert progress event to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "stage": self.stage,
            "detail": self.detail,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgressEvent:
        """Create progress event from dictionary."""
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            stage=data["stage"],
            detail=data["detail"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )

    def is_stage(self, stage: str) -> bool:
        """Check if this event is for a specific stage."""
        return self.stage == stage

    def has_error(self) -> bool:
        """Check if this event indicates an error."""
        return self.stage == "error" or "error" in self.detail.lower()

    def is_completion(self) -> bool:
        """Check if this event indicates completion."""
        return self.stage == "completed" or "completed" in self.detail.lower()

    def needs_approval(self) -> bool:
        """Check if this event indicates approval is needed."""
        return (
            "approval" in self.detail.lower()
            or "confirm" in self.detail.lower()
            or "permission" in self.detail.lower()
        )