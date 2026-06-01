"""Session data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SessionStatus(Enum):
    """Session status enumeration."""

    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class Session:
    """Session data model representing a Cursor session."""

    id: str
    name: str
    status: SessionStatus
    adapter: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_new(
        self,
        name: str,
        adapter: str,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new session with generated ID and timestamps."""
        now = datetime.utcnow()
        return Session(
            id=str(uuid.uuid4()),
            name=name,
            status=SessionStatus.IDLE,
            adapter=adapter,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def update_status(self, status: SessionStatus) -> None:
        """Update session status and updated_at timestamp."""
        self.status = status
        self.updated_at = datetime.utcnow()

    def update_metadata(self, metadata: dict[str, Any]) -> None:
        """Update session metadata and updated_at timestamp."""
        self.metadata.update(metadata)
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "adapter": self.adapter,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Create session from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            status=SessionStatus(data["status"]),
            adapter=data["adapter"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )