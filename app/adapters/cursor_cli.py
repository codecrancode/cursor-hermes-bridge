"""Cursor CLI adapter - uses Cursor Agent CLI for interaction."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models.command_request import CommandType
from ..models.command_result import CommandResult
from ..models.progress_event import ProgressEvent
from ..models.session import Session, SessionStatus
from ..utils.logging import get_logger
from .base import (
    AdapterUnavailableError,
    CommunicationError,
    CursorAdapter,
    SessionNotFoundError,
    TimeoutError,
)

logger = get_logger("app.adapters.cursor_cli")


class CursorCLIAdapter(CursorAdapter):
    """Adapter that uses the Cursor Agent CLI for bidirectional communication."""

    def __init__(self) -> None:
        self._cli_path: str | None = None
        self._initialized = False
        self._command_timeout = 30  # seconds

    @property
    def name(self) -> str:
        return "cursor_cli"

    @property
    def description(self) -> str:
        return "Uses Cursor Agent CLI for full bidirectional communication"

    async def initialize(self) -> None:
        """Initialize the adapter and locate Cursor CLI."""
        if self._initialized:
            return

        logger.info("Initializing cursor CLI adapter")

        # Try to find cursor CLI executable
        self._cli_path = await self._find_cursor_cli()

        if not self._cli_path:
            raise AdapterUnavailableError("Cursor CLI not found", self.name)

        # Verify CLI is working
        try:
            result = await self._run_command(["--version"])
            if not result["success"]:
                raise AdapterUnavailableError("Cursor CLI not responding", self.name)

            logger.info("Cursor CLI adapter initialized", extra={
                "cli_path": self._cli_path,
                "version": result.get("output", "").strip()
            })

        except Exception as e:
            raise AdapterUnavailableError(f"Failed to initialize CLI: {e}", self.name)

        self._initialized = True

    async def cleanup(self) -> None:
        """Clean up adapter resources."""
        self._initialized = False
        logger.info("Cleaned up cursor CLI adapter")

    def is_available(self) -> bool:
        """Check if Cursor CLI is available."""
        return self._cli_path is not None and shutil.which(self._cli_path) is not None

    def get_capabilities(self) -> dict[str, bool]:
        """Get adapter capabilities."""
        capabilities = super().get_capabilities()
        capabilities.update({
            "send_prompt": True,
            "continue_session": True,
            "stop_session": True,
            "new_session": True,
            "switch_session": True,
            "real_time_monitoring": True,
            "bidirectional_communication": True,
            "file_operations": True,
        })
        return capabilities

    async def get_status(self) -> dict[str, Any]:
        """Get current Cursor status via CLI."""
        if not self.is_available():
            raise AdapterUnavailableError("Cursor CLI not available", self.name)

        try:
            result = await self._run_command(["status", "--json"])
            if result["success"]:
                status_data = json.loads(result["output"])
                return {
                    "is_running": status_data.get("running", False),
                    "current_session": status_data.get("current_session"),
                    "workspace": status_data.get("workspace"),
                    "last_activity": status_data.get("last_activity"),
                    "adapter": self.name,
                }
            else:
                raise CommunicationError(f"CLI status failed: {result['error']}", self.name)

        except json.JSONDecodeError as e:
            raise CommunicationError(f"Failed to parse CLI response: {e}", self.name)
        except Exception as e:
            raise CommunicationError(f"CLI communication error: {e}", self.name)

    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult:
        """Send a prompt to the specified session via CLI."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.SEND,
                error="Cursor CLI not available",
                session_id=session_id
            )

        start_time = datetime.utcnow()

        try:
            result = await self._run_command([
                "send",
                "--session", session_id,
                "--prompt", prompt,
                "--json"
            ])

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if result["success"]:
                response_data = json.loads(result["output"])
                return CommandResult.create_success(
                    request_id="",
                    command=CommandType.SEND,
                    output=response_data.get("response", "Prompt sent successfully"),
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response_data
                )
            else:
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.SEND,
                    error=result["error"],
                    session_id=session_id,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.SEND,
                error=f"CLI error: {str(e)}",
                session_id=session_id,
                duration_ms=duration_ms
            )

    async def continue_session(self, session_id: str) -> CommandResult:
        """Continue execution in the specified session via CLI."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.CONTINUE,
                error="Cursor CLI not available",
                session_id=session_id
            )

        start_time = datetime.utcnow()

        try:
            result = await self._run_command([
                "continue",
                "--session", session_id,
                "--json"
            ])

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if result["success"]:
                response_data = json.loads(result["output"])
                return CommandResult.create_success(
                    request_id="",
                    command=CommandType.CONTINUE,
                    output=response_data.get("message", "Session continued"),
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response_data
                )
            else:
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.CONTINUE,
                    error=result["error"],
                    session_id=session_id,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.CONTINUE,
                error=f"CLI error: {str(e)}",
                session_id=session_id,
                duration_ms=duration_ms
            )

    async def stop_session(self, session_id: str) -> CommandResult:
        """Stop execution in the specified session via CLI."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.STOP,
                error="Cursor CLI not available",
                session_id=session_id
            )

        start_time = datetime.utcnow()

        try:
            result = await self._run_command([
                "stop",
                "--session", session_id,
                "--json"
            ])

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if result["success"]:
                response_data = json.loads(result["output"])
                return CommandResult.create_success(
                    request_id="",
                    command=CommandType.STOP,
                    output=response_data.get("message", "Session stopped"),
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response_data
                )
            else:
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.STOP,
                    error=result["error"],
                    session_id=session_id,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.STOP,
                error=f"CLI error: {str(e)}",
                session_id=session_id,
                duration_ms=duration_ms
            )

    async def new_session(self, name: str | None = None) -> CommandResult:
        """Create a new session via CLI."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.NEW,
                error="Cursor CLI not available"
            )

        start_time = datetime.utcnow()

        try:
            cmd = ["new", "--json"]
            if name:
                cmd.extend(["--name", name])

            result = await self._run_command(cmd)
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if result["success"]:
                response_data = json.loads(result["output"])
                session_id = response_data.get("session_id")
                return CommandResult.create_success(
                    request_id="",
                    command=CommandType.NEW,
                    output=f"Created new session: {session_id}",
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response_data
                )
            else:
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.NEW,
                    error=result["error"],
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.NEW,
                error=f"CLI error: {str(e)}",
                duration_ms=duration_ms
            )

    async def list_sessions(self) -> list[Session]:
        """List all sessions via CLI."""
        if not self.is_available():
            return []

        try:
            result = await self._run_command(["sessions", "--json"])
            if result["success"]:
                sessions_data = json.loads(result["output"])
                sessions = []

                for session_data in sessions_data.get("sessions", []):
                    session = Session(
                        id=session_data["id"],
                        name=session_data.get("name", session_data["id"]),
                        status=SessionStatus(session_data.get("status", "idle")),
                        adapter=self.name,
                        created_at=datetime.fromisoformat(session_data["created_at"]),
                        updated_at=datetime.fromisoformat(session_data["updated_at"]),
                        metadata=session_data.get("metadata", {})
                    )
                    sessions.append(session)

                return sessions

            else:
                logger.error("Failed to list sessions", extra={"error": result["error"]})
                return []

        except Exception as e:
            logger.error("CLI error listing sessions", extra={"error": str(e)})
            return []

    async def switch_session(self, session_id: str) -> CommandResult:
        """Switch to the specified session via CLI."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.SWITCH,
                error="Cursor CLI not available",
                session_id=session_id
            )

        start_time = datetime.utcnow()

        try:
            result = await self._run_command([
                "switch",
                "--session", session_id,
                "--json"
            ])

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if result["success"]:
                response_data = json.loads(result["output"])
                return CommandResult.create_success(
                    request_id="",
                    command=CommandType.SWITCH,
                    output=f"Switched to session {session_id}",
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response_data
                )
            else:
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.SWITCH,
                    error=result["error"],
                    session_id=session_id,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.SWITCH,
                error=f"CLI error: {str(e)}",
                session_id=session_id,
                duration_ms=duration_ms
            )

    async def get_session_summary(self, session_id: str) -> str:
        """Get session summary via CLI."""
        try:
            result = await self._run_command([
                "summary",
                "--session", session_id,
                "--json"
            ])

            if result["success"]:
                summary_data = json.loads(result["output"])
                return summary_data.get("summary", f"No summary available for session {session_id}")
            else:
                return f"Error getting summary: {result['error']}"

        except Exception as e:
            return f"CLI error: {str(e)}"

    async def tail_session(self, session_id: str, lines: int = 20) -> str:
        """Get last N lines from session via CLI."""
        try:
            result = await self._run_command([
                "tail",
                "--session", session_id,
                "--lines", str(lines),
                "--json"
            ])

            if result["success"]:
                tail_data = json.loads(result["output"])
                return tail_data.get("output", f"No output available for session {session_id}")
            else:
                return f"Error getting tail: {result['error']}"

        except Exception as e:
            return f"CLI error: {str(e)}"

    async def get_progress(self, session_id: str) -> list[ProgressEvent]:
        """Get progress events via CLI."""
        try:
            result = await self._run_command([
                "progress",
                "--session", session_id,
                "--json"
            ])

            if result["success"]:
                progress_data = json.loads(result["output"])
                events = []

                for event_data in progress_data.get("events", []):
                    event = ProgressEvent(
                        id=event_data["id"],
                        session_id=session_id,
                        stage=event_data["stage"],
                        detail=event_data["detail"],
                        timestamp=datetime.fromisoformat(event_data["timestamp"]),
                        metadata=event_data.get("metadata", {})
                    )
                    events.append(event)

                return events
            else:
                logger.error("Failed to get progress", extra={
                    "session_id": session_id,
                    "error": result["error"]
                })
                return []

        except Exception as e:
            logger.error("CLI error getting progress", extra={
                "session_id": session_id,
                "error": str(e)
            })
            return []

    async def get_workspace_info(self) -> dict[str, Any]:
        """Get workspace information via CLI."""
        try:
            result = await self._run_command(["workspace", "--json"])
            if result["success"]:
                return json.loads(result["output"])
            else:
                return {"error": result["error"]}
        except Exception as e:
            return {"error": str(e)}

    # Helper methods

    async def _find_cursor_cli(self) -> str | None:
        """Find the Cursor CLI executable."""
        # Common CLI names and paths
        cli_names = ["cursor", "cursor-cli", "cursor-agent"]
        common_paths = [
            "/usr/local/bin",
            "/opt/cursor/bin",
            "~/.cursor/bin",
            "/Applications/Cursor.app/Contents/Resources/bin",  # macOS
        ]

        # First, try to find in PATH
        for name in cli_names:
            cli_path = shutil.which(name)
            if cli_path:
                logger.debug("Found Cursor CLI in PATH", extra={"path": cli_path})
                return cli_path

        # Then try common installation paths
        for path_str in common_paths:
            path = Path(path_str).expanduser()
            for name in cli_names:
                cli_path = path / name
                if cli_path.exists() and cli_path.is_file():
                    logger.debug("Found Cursor CLI in common path", extra={"path": str(cli_path)})
                    return str(cli_path)

        logger.warning("Cursor CLI not found in PATH or common locations")
        return None

    async def _run_command(self, args: list[str]) -> dict[str, Any]:
        """Run a CLI command and return the result."""
        if not self._cli_path:
            return {
                "success": False,
                "output": "",
                "error": "CLI path not set"
            }

        cmd = [self._cli_path] + args
        logger.debug("Running CLI command", extra={"command": " ".join(cmd)})

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._command_timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise TimeoutError(f"CLI command timed out after {self._command_timeout}s", self.name)

            stdout_text = stdout.decode("utf-8") if stdout else ""
            stderr_text = stderr.decode("utf-8") if stderr else ""

            success = process.returncode == 0

            logger.debug("CLI command completed", extra={
                "command": " ".join(cmd),
                "return_code": process.returncode,
                "success": success
            })

            return {
                "success": success,
                "output": stdout_text.strip(),
                "error": stderr_text.strip() if not success else "",
                "return_code": process.returncode
            }

        except Exception as e:
            logger.error("CLI command failed", extra={
                "command": " ".join(cmd),
                "error": str(e)
            })
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "return_code": -1
            }