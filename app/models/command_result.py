"""Command result data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .command_request import CommandType


@dataclass
class CommandResult:
    """Command result data model representing the result of a command execution."""

    id: str
    request_id: str
    success: bool
    output: str | None
    error: str | None
    session_id: str | None
    command: CommandType
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create_success(
        cls,
        request_id: str,
        command: CommandType,
        output: str | None = None,
        session_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Create a successful command result."""
        return cls(
            id=str(uuid.uuid4()),
            request_id=request_id,
            success=True,
            output=output,
            error=None,
            session_id=session_id,
            command=command,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

    @classmethod
    def create_error(
        cls,
        request_id: str,
        command: CommandType,
        error: str,
        session_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Create an error command result."""
        return cls(
            id=str(uuid.uuid4()),
            request_id=request_id,
            success=False,
            output=None,
            error=error,
            session_id=session_id,
            command=command,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert command result to dictionary for serialization."""
        return {
            "id": self.id,
            "request_id": self.request_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "session_id": self.session_id,
            "command": self.command.value,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandResult:
        """Create command result from dictionary."""
        return cls(
            id=data["id"],
            request_id=data["request_id"],
            success=data["success"],
            output=data.get("output"),
            error=data.get("error"),
            session_id=data.get("session_id"),
            command=CommandType(data["command"]),
            duration_ms=data.get("duration_ms"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def is_success(self) -> bool:
        """Check if the command was successful."""
        return self.success

    def is_error(self) -> bool:
        """Check if the command had an error."""
        return not self.success

    def get_message(self) -> str:
        """Get the appropriate message (output if success, error if failure)."""
        if self.success:
            return self.output or "Command completed successfully"
        else:
            return self.error or "Command failed with unknown error"

    def has_output(self) -> bool:
        """Check if the result has output."""
        return self.output is not None and len(self.output.strip()) > 0