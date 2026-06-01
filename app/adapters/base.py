"""Base adapter interface for Cursor integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models.command_result import CommandResult
from ..models.progress_event import ProgressEvent
from ..models.session import Session


class CursorAdapter(ABC):
    """Abstract base class for Cursor adapters.

    Defines the interface that all Cursor adapters must implement
    to provide consistent interaction with Cursor IDE.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this adapter."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of this adapter."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the adapter and any required resources."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up adapter resources."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this adapter is available and can be used."""

    @abstractmethod
    async def get_status(self) -> dict[str, Any]:
        """Get the current status of Cursor.

        Returns:
            Dictionary containing status information like:
            - is_running: bool
            - current_session: str | None
            - active_workspace: str | None
            - last_activity: str | None
        """

    @abstractmethod
    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult:
        """Send a prompt to the specified session.

        Args:
            session_id: The session to send the prompt to
            prompt: The prompt text to send

        Returns:
            CommandResult indicating success/failure and any output
        """

    @abstractmethod
    async def continue_session(self, session_id: str) -> CommandResult:
        """Continue execution in the specified session.

        Args:
            session_id: The session to continue

        Returns:
            CommandResult indicating success/failure and any output
        """

    @abstractmethod
    async def stop_session(self, session_id: str) -> CommandResult:
        """Stop execution in the specified session.

        Args:
            session_id: The session to stop

        Returns:
            CommandResult indicating success/failure and any output
        """

    @abstractmethod
    async def new_session(self, name: str | None = None) -> CommandResult:
        """Create a new session.

        Args:
            name: Optional name for the new session

        Returns:
            CommandResult with the new session information
        """

    @abstractmethod
    async def list_sessions(self) -> list[Session]:
        """List all available sessions.

        Returns:
            List of Session objects
        """

    @abstractmethod
    async def switch_session(self, session_id: str) -> CommandResult:
        """Switch to the specified session.

        Args:
            session_id: The session to switch to

        Returns:
            CommandResult indicating success/failure
        """

    @abstractmethod
    async def get_session_summary(self, session_id: str) -> str:
        """Get a summary of the specified session.

        Args:
            session_id: The session to summarize

        Returns:
            Human-readable summary of the session
        """

    @abstractmethod
    async def tail_session(self, session_id: str, lines: int = 20) -> str:
        """Get the last N lines of output from a session.

        Args:
            session_id: The session to tail
            lines: Number of lines to retrieve

        Returns:
            The last N lines of session output
        """

    @abstractmethod
    async def get_progress(self, session_id: str) -> list[ProgressEvent]:
        """Get progress events for the specified session.

        Args:
            session_id: The session to get progress for

        Returns:
            List of ProgressEvent objects
        """

    @abstractmethod
    async def get_workspace_info(self) -> dict[str, Any]:
        """Get information about the current workspace.

        Returns:
            Dictionary containing workspace information like:
            - path: str
            - name: str
            - files_count: int
            - git_status: dict | None
        """

    # Optional methods that adapters can override

    async def validate_session_id(self, session_id: str) -> bool:
        """Validate that a session ID exists and is accessible.

        Args:
            session_id: The session ID to validate

        Returns:
            True if the session is valid, False otherwise
        """
        sessions = await self.list_sessions()
        return any(session.id == session_id for session in sessions)

    async def get_adapter_info(self) -> dict[str, Any]:
        """Get information about this adapter.

        Returns:
            Dictionary containing adapter information
        """
        return {
            "name": self.name,
            "description": self.description,
            "is_available": self.is_available(),
            "capabilities": self.get_capabilities(),
        }

    def get_capabilities(self) -> dict[str, bool]:
        """Get the capabilities supported by this adapter.

        Returns:
            Dictionary mapping capability names to support status
        """
        return {
            "send_prompt": True,
            "continue_session": True,
            "stop_session": True,
            "new_session": True,
            "list_sessions": True,
            "switch_session": True,
            "get_summary": True,
            "tail_session": True,
            "get_progress": True,
            "workspace_info": True,
            "real_time_monitoring": False,  # Override in subclasses
            "bidirectional_communication": False,  # Override in subclasses
            "file_operations": False,  # Override in subclasses
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check of the adapter.

        Returns:
            Dictionary containing health check results
        """
        try:
            status = await self.get_status()
            return {
                "healthy": True,
                "adapter": self.name,
                "status": status,
                "error": None,
            }
        except Exception as e:
            return {
                "healthy": False,
                "adapter": self.name,
                "status": None,
                "error": str(e),
            }


class AdapterError(Exception):
    """Base exception class for adapter errors."""

    def __init__(self, message: str, adapter_name: str | None = None) -> None:
        super().__init__(message)
        self.adapter_name = adapter_name


class AdapterUnavailableError(AdapterError):
    """Raised when an adapter is not available."""


class SessionNotFoundError(AdapterError):
    """Raised when a requested session cannot be found."""


class CommunicationError(AdapterError):
    """Raised when communication with Cursor fails."""


class InvalidOperationError(AdapterError):
    """Raised when an invalid operation is attempted."""


class TimeoutError(AdapterError):
    """Raised when an operation times out."""


# Adapter registry for managing multiple adapters

class AdapterRegistry:
    """Registry for managing available Cursor adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, CursorAdapter] = {}
        self._primary_adapter: str | None = None

    def register(self, adapter: CursorAdapter) -> None:
        """Register an adapter.

        Args:
            adapter: The adapter instance to register
        """
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        """Unregister an adapter.

        Args:
            name: The name of the adapter to unregister
        """
        if name in self._adapters:
            del self._adapters[name]
            if self._primary_adapter == name:
                self._primary_adapter = None

    def get(self, name: str) -> CursorAdapter | None:
        """Get an adapter by name.

        Args:
            name: The name of the adapter

        Returns:
            The adapter instance or None if not found
        """
        return self._adapters.get(name)

    def list_available(self) -> list[CursorAdapter]:
        """Get a list of all available adapters.

        Returns:
            List of available adapter instances
        """
        return [adapter for adapter in self._adapters.values() if adapter.is_available()]

    def get_primary(self) -> CursorAdapter | None:
        """Get the primary adapter.

        Returns:
            The primary adapter instance or None if not set
        """
        if self._primary_adapter:
            return self._adapters.get(self._primary_adapter)

        # Fall back to first available adapter
        available = self.list_available()
        return available[0] if available else None

    def set_primary(self, name: str) -> bool:
        """Set the primary adapter.

        Args:
            name: The name of the adapter to set as primary

        Returns:
            True if successful, False if adapter not found or unavailable
        """
        adapter = self._adapters.get(name)
        if adapter and adapter.is_available():
            self._primary_adapter = name
            return True
        return False

    def get_adapter_info(self) -> list[dict[str, Any]]:
        """Get information about all registered adapters.

        Returns:
            List of adapter information dictionaries
        """
        info = []
        for adapter in self._adapters.values():
            adapter_info = {
                "name": adapter.name,
                "description": adapter.description,
                "is_available": adapter.is_available(),
                "is_primary": self._primary_adapter == adapter.name,
                "capabilities": adapter.get_capabilities(),
            }
            info.append(adapter_info)
        return info

    async def health_check_all(self) -> dict[str, dict[str, Any]]:
        """Perform health checks on all adapters.

        Returns:
            Dictionary mapping adapter names to health check results
        """
        results = {}
        for adapter in self._adapters.values():
            results[adapter.name] = await adapter.health_check()
        return results


# Global adapter registry instance
adapter_registry = AdapterRegistry()