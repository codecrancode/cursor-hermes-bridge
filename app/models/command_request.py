"""Command request data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CommandType(Enum):
    """Command type enumeration."""

    SEND = "send"
    CONTINUE = "continue"
    STOP = "stop"
    NEW = "new"
    STATUS = "status"
    SWITCH = "switch"
    SUMMARY = "summary"
    TAIL = "tail"
    LIST_SESSIONS = "list_sessions"


@dataclass
class CommandRequest:
    """Command request data model representing a command to execute."""

    id: str
    session_id: str | None
    command: CommandType
    params: dict[str, Any]
    created_at: datetime
    chat_id: int | None = None
    user_id: int | None = None

    @classmethod
    def create_new(
        self,
        command: CommandType | str,
        session_id: str | None = None,
        params: dict[str, Any] | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
    ) -> CommandRequest:
        """Create a new command request with generated ID and current timestamp."""
        if isinstance(command, str):
            command = CommandType(command)

        return CommandRequest(
            id=str(uuid.uuid4()),
            session_id=session_id,
            command=command,
            params=params or {},
            created_at=datetime.utcnow(),
            chat_id=chat_id,
            user_id=user_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert command request to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "command": self.command.value,
            "params": self.params,
            "created_at": self.created_at.isoformat(),
            "chat_id": self.chat_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandRequest:
        """Create command request from dictionary."""
        return cls(
            id=data["id"],
            session_id=data.get("session_id"),
            command=CommandType(data["command"]),
            params=data.get("params", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            chat_id=data.get("chat_id"),
            user_id=data.get("user_id"),
        )

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a parameter value with optional default."""
        return self.params.get(key, default)

    def has_param(self, key: str) -> bool:
        """Check if a parameter exists."""
        return key in self.params

    def requires_session(self) -> bool:
        """Check if this command requires an active session."""
        return self.command in {
            CommandType.SEND,
            CommandType.CONTINUE,
            CommandType.STOP,
            CommandType.SWITCH,
            CommandType.SUMMARY,
            CommandType.TAIL,
        }