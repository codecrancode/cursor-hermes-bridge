"""Test fixtures for the Cursor-Hermes Bridge."""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path

from app.adapters.base import CursorAdapter, adapter_registry
from app.models.command_result import CommandResult
from app.models.session import Session, SessionStatus
from app.storage.database import Database
from app.services.auth_service import AuthService
from app.services.session_service import SessionService
from app.services.progress_service import ProgressService


class MockAdapter(CursorAdapter):
    """Mock adapter for testing with all abstract methods implemented."""

    def __init__(self, name: str = "mock", available: bool = True):
        self._name = name
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Mock adapter for testing"

    async def initialize(self) -> None:
        pass

    async def cleanup(self) -> None:
        pass

    async def get_status(self) -> dict:
        return {"status": "idle", "adapter": self._name}

    async def get_workspace_info(self) -> dict:
        return {"workspace": "/mock", "project": "test"}

    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult:
        return CommandResult(success=True, output=f"Sent: {prompt}", error=None, session_id=session_id, command="send")

    async def continue_session(self, session_id: str) -> CommandResult:
        return CommandResult(success=True, output="Continued", error=None, session_id=session_id, command="continue")

    async def stop_session(self, session_id: str) -> CommandResult:
        return CommandResult(success=True, output="Stopped", error=None, session_id=session_id, command="stop")

    async def new_session(self) -> CommandResult:
        return CommandResult(success=True, output="New session created", error=None, session_id="mock-new", command="new")

    async def list_sessions(self) -> list[Session]:
        return []

    async def switch_session(self, session_id: str) -> CommandResult:
        return CommandResult(success=True, output=f"Switched to {session_id}", error=None, session_id=session_id, command="switch")

    async def get_session_summary(self, session_id: str) -> str:
        return "Mock session summary"

    async def tail_session(self, session_id: str, lines: int = 20) -> str:
        return "Mock tail output"

    async def get_progress(self, session_id: str) -> list:
        return []

    def is_available(self) -> bool:
        return self._available


# Register mock adapter globally
_adapter_registered = False


def ensure_mock_adapter():
    global _adapter_registered
    if not _adapter_registered:
        mock = MockAdapter()
        adapter_registry.register(mock)
        adapter_registry.set_primary("mock")
        _adapter_registered = True


@pytest.fixture(autouse=True)
def auto_ensure_mock():
    ensure_mock_adapter()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[Database, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database = Database(tmp.name)
    await database.initialize()
    yield database
    await database.close()
    Path(tmp.name).unlink(missing_ok=True)


@pytest_asyncio.fixture
async def session_service(db: Database) -> SessionService:
    return SessionService(db)


@pytest_asyncio.fixture
async def progress_service(db: Database) -> ProgressService:
    return ProgressService(db)


@pytest_asyncio.fixture
def auth_service(db: Database) -> AuthService:
    return AuthService(db)
