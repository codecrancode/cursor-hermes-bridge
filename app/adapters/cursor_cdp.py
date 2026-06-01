"""Cursor CDP adapter - experimental Chrome DevTools Protocol integration."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from ..models.command_request import CommandType
from ..models.command_result import CommandResult
from ..models.progress_event import ProgressEvent
from ..models.session import Session, SessionStatus
from ..utils.config import settings
from ..utils.logging import get_logger
from .base import (
    AdapterUnavailableError,
    CommunicationError,
    CursorAdapter,
    SessionNotFoundError,
    TimeoutError,
)

logger = get_logger("app.adapters.cursor_cdp")


class CursorCDPAdapter(CursorAdapter):
    """Experimental adapter using Chrome DevTools Protocol for Cursor integration.

    This adapter is feature-flagged and requires the websockets library.
    It attempts to communicate with Cursor through Chrome DevTools Protocol
    if Cursor exposes a CDP endpoint.
    """

    def __init__(self) -> None:
        self._ws_url: str | None = None
        self._websocket: WebSocketClientProtocol | None = None
        self._initialized = False
        self._connection_timeout = 10  # seconds
        self._command_timeout = 30  # seconds
        self._message_id = 0

    @property
    def name(self) -> str:
        return "cursor_cdp"

    @property
    def description(self) -> str:
        return "Experimental Chrome DevTools Protocol integration (feature-flagged)"

    async def initialize(self) -> None:
        """Initialize the CDP adapter and attempt connection."""
        if self._initialized:
            return

        if not settings.ENABLE_CDP_ADAPTER:
            raise AdapterUnavailableError("CDP adapter is disabled by feature flag", self.name)

        if not WEBSOCKETS_AVAILABLE:
            raise AdapterUnavailableError("websockets library not available", self.name)

        logger.info("Initializing cursor CDP adapter")

        # Try to discover CDP endpoint
        self._ws_url = await self._discover_cdp_endpoint()
        if not self._ws_url:
            raise AdapterUnavailableError("CDP endpoint not found", self.name)

        # Attempt connection
        try:
            await self._connect()
            logger.info("CDP adapter initialized", extra={"ws_url": self._ws_url})
        except Exception as e:
            raise AdapterUnavailableError(f"Failed to connect to CDP: {e}", self.name)

        self._initialized = True

    async def cleanup(self) -> None:
        """Clean up CDP connection."""
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.warning("Error closing CDP websocket", extra={"error": str(e)})
            finally:
                self._websocket = None

        self._initialized = False
        logger.info("Cleaned up cursor CDP adapter")

    def is_available(self) -> bool:
        """Check if CDP adapter is available."""
        return (
            settings.ENABLE_CDP_ADAPTER and
            WEBSOCKETS_AVAILABLE and
            self._ws_url is not None
        )

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
        """Get current Cursor status via CDP."""
        if not self.is_available():
            raise AdapterUnavailableError("CDP adapter not available", self.name)

        try:
            await self._ensure_connected()

            # Send CDP command to get runtime information
            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": "window.cursor && window.cursor.getStatus ? window.cursor.getStatus() : {}"
            })

            if "result" in response and "value" in response["result"]:
                cursor_status = response["result"]["value"]
                return {
                    "is_running": True,  # If we can connect, it's running
                    "current_session": cursor_status.get("currentSession"),
                    "workspace": cursor_status.get("workspace"),
                    "last_activity": cursor_status.get("lastActivity"),
                    "adapter": self.name,
                }
            else:
                return {
                    "is_running": True,
                    "current_session": None,
                    "workspace": None,
                    "last_activity": None,
                    "adapter": self.name,
                }

        except Exception as e:
            raise CommunicationError(f"CDP status error: {e}", self.name)

    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult:
        """Send prompt via CDP."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.SEND,
                error="CDP adapter not available",
                session_id=session_id
            )

        start_time = datetime.utcnow()

        try:
            await self._ensure_connected()

            # Send CDP command to execute prompt
            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": f"""
                if (window.cursor && window.cursor.sendPrompt) {{
                    window.cursor.sendPrompt('{session_id}', {json.dumps(prompt)})
                }} else {{
                    throw new Error('Cursor API not available');
                }}
                """
            })

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if "result" in response:
                if "exceptionDetails" in response:
                    error_msg = response["exceptionDetails"].get("text", "Unknown error")
                    return CommandResult.create_error(
                        request_id="",
                        command=CommandType.SEND,
                        error=f"CDP error: {error_msg}",
                        session_id=session_id,
                        duration_ms=duration_ms
                    )
                else:
                    result_value = response["result"].get("value", "Prompt sent")
                    return CommandResult.create_success(
                        request_id="",
                        command=CommandType.SEND,
                        output=str(result_value),
                        session_id=session_id,
                        duration_ms=duration_ms,
                        metadata=response
                    )
            else:
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.SEND,
                    error="Invalid CDP response",
                    session_id=session_id,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.SEND,
                error=f"CDP error: {str(e)}",
                session_id=session_id,
                duration_ms=duration_ms
            )

    async def continue_session(self, session_id: str) -> CommandResult:
        """Continue session via CDP."""
        return await self._execute_session_command("continue", session_id, CommandType.CONTINUE)

    async def stop_session(self, session_id: str) -> CommandResult:
        """Stop session via CDP."""
        return await self._execute_session_command("stop", session_id, CommandType.STOP)

    async def new_session(self, name: str | None = None) -> CommandResult:
        """Create new session via CDP."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=CommandType.NEW,
                error="CDP adapter not available"
            )

        start_time = datetime.utcnow()

        try:
            await self._ensure_connected()

            name_param = json.dumps(name) if name else "null"
            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": f"""
                if (window.cursor && window.cursor.newSession) {{
                    window.cursor.newSession({name_param})
                }} else {{
                    throw new Error('Cursor API not available');
                }}
                """
            })

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if "result" in response and "exceptionDetails" not in response:
                result_value = response["result"].get("value", {})
                session_id = result_value.get("sessionId") if isinstance(result_value, dict) else None
                return CommandResult.create_success(
                    request_id="",
                    command=CommandType.NEW,
                    output=f"Created session: {session_id}",
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response
                )
            else:
                error_msg = response.get("exceptionDetails", {}).get("text", "Unknown error")
                return CommandResult.create_error(
                    request_id="",
                    command=CommandType.NEW,
                    error=f"CDP error: {error_msg}",
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=CommandType.NEW,
                error=f"CDP error: {str(e)}",
                duration_ms=duration_ms
            )

    async def list_sessions(self) -> list[Session]:
        """List sessions via CDP."""
        try:
            await self._ensure_connected()

            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": """
                if (window.cursor && window.cursor.getSessions) {
                    window.cursor.getSessions()
                } else {
                    []
                }
                """
            })

            if "result" in response and "value" in response["result"]:
                sessions_data = response["result"]["value"]
                sessions = []

                if isinstance(sessions_data, list):
                    for session_data in sessions_data:
                        if isinstance(session_data, dict):
                            session = Session(
                                id=session_data.get("id", "unknown"),
                                name=session_data.get("name", "Unknown"),
                                status=SessionStatus(session_data.get("status", "idle")),
                                adapter=self.name,
                                created_at=datetime.fromisoformat(session_data.get("createdAt", datetime.utcnow().isoformat())),
                                updated_at=datetime.fromisoformat(session_data.get("updatedAt", datetime.utcnow().isoformat())),
                                metadata=session_data.get("metadata", {})
                            )
                            sessions.append(session)

                return sessions
            else:
                return []

        except Exception as e:
            logger.error("CDP error listing sessions", extra={"error": str(e)})
            return []

    async def switch_session(self, session_id: str) -> CommandResult:
        """Switch session via CDP."""
        return await self._execute_session_command("switch", session_id, CommandType.SWITCH)

    async def get_session_summary(self, session_id: str) -> str:
        """Get session summary via CDP."""
        try:
            await self._ensure_connected()

            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": f"""
                if (window.cursor && window.cursor.getSessionSummary) {{
                    window.cursor.getSessionSummary('{session_id}')
                }} else {{
                    'Summary not available'
                }}
                """
            })

            if "result" in response and "value" in response["result"]:
                return str(response["result"]["value"])
            else:
                return f"Error getting summary for session {session_id}"

        except Exception as e:
            return f"CDP error: {str(e)}"

    async def tail_session(self, session_id: str, lines: int = 20) -> str:
        """Get session tail via CDP."""
        try:
            await self._ensure_connected()

            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": f"""
                if (window.cursor && window.cursor.tailSession) {{
                    window.cursor.tailSession('{session_id}', {lines})
                }} else {{
                    'Tail not available'
                }}
                """
            })

            if "result" in response and "value" in response["result"]:
                return str(response["result"]["value"])
            else:
                return f"Error getting tail for session {session_id}"

        except Exception as e:
            return f"CDP error: {str(e)}"

    async def get_progress(self, session_id: str) -> list[ProgressEvent]:
        """Get progress events via CDP."""
        try:
            await self._ensure_connected()

            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": f"""
                if (window.cursor && window.cursor.getProgress) {{
                    window.cursor.getProgress('{session_id}')
                }} else {{
                    []
                }}
                """
            })

            if "result" in response and "value" in response["result"]:
                events_data = response["result"]["value"]
                events = []

                if isinstance(events_data, list):
                    for event_data in events_data:
                        if isinstance(event_data, dict):
                            event = ProgressEvent(
                                id=event_data.get("id", "unknown"),
                                session_id=session_id,
                                stage=event_data.get("stage", "unknown"),
                                detail=event_data.get("detail", ""),
                                timestamp=datetime.fromisoformat(event_data.get("timestamp", datetime.utcnow().isoformat())),
                                metadata=event_data.get("metadata", {})
                            )
                            events.append(event)

                return events
            else:
                return []

        except Exception as e:
            logger.error("CDP error getting progress", extra={
                "session_id": session_id,
                "error": str(e)
            })
            return []

    async def get_workspace_info(self) -> dict[str, Any]:
        """Get workspace info via CDP."""
        try:
            await self._ensure_connected()

            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": """
                if (window.cursor && window.cursor.getWorkspaceInfo) {
                    window.cursor.getWorkspaceInfo()
                } else {
                    {}
                }
                """
            })

            if "result" in response and "value" in response["result"]:
                return response["result"]["value"]
            else:
                return {}

        except Exception as e:
            return {"error": str(e)}

    # Helper methods

    async def _discover_cdp_endpoint(self) -> str | None:
        """Attempt to discover Cursor's CDP endpoint."""
        # Common CDP ports that Cursor might use
        candidate_ports = [9222, 9223, 9224, 9333, 9444]

        for port in candidate_ports:
            try:
                # Try to connect to potential CDP endpoint
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://localhost:{port}/json/version",
                        timeout=2.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        # Look for Cursor-like user agent or product name
                        if any(keyword in str(data).lower() for keyword in ["cursor", "electron"]):
                            ws_url = f"ws://localhost:{port}/devtools/page"
                            logger.info("Discovered potential CDP endpoint", extra={
                                "port": port,
                                "ws_url": ws_url
                            })
                            return ws_url
            except Exception:
                continue

        logger.warning("Could not discover CDP endpoint")
        return None

    async def _connect(self) -> None:
        """Connect to the CDP endpoint."""
        if not self._ws_url:
            raise CommunicationError("No CDP URL available", self.name)

        try:
            self._websocket = await asyncio.wait_for(
                websockets.connect(self._ws_url),
                timeout=self._connection_timeout
            )
            logger.debug("Connected to CDP endpoint", extra={"url": self._ws_url})
        except asyncio.TimeoutError:
            raise TimeoutError(f"CDP connection timeout after {self._connection_timeout}s", self.name)

    async def _ensure_connected(self) -> None:
        """Ensure CDP connection is active."""
        if not self._websocket or self._websocket.closed:
            await self._connect()

    async def _send_cdp_command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a CDP command and wait for response."""
        if not self._websocket:
            raise CommunicationError("No active CDP connection", self.name)

        self._message_id += 1
        command = {
            "id": self._message_id,
            "method": method,
            "params": params or {}
        }

        try:
            await self._websocket.send(json.dumps(command))

            # Wait for response with matching ID
            while True:
                response_str = await asyncio.wait_for(
                    self._websocket.recv(),
                    timeout=self._command_timeout
                )
                response = json.loads(response_str)

                if response.get("id") == self._message_id:
                    return response

                # Ignore other messages (events, other responses)

        except asyncio.TimeoutError:
            raise TimeoutError(f"CDP command timeout after {self._command_timeout}s", self.name)
        except Exception as e:
            raise CommunicationError(f"CDP command failed: {e}", self.name)

    async def _execute_session_command(
        self,
        command: str,
        session_id: str,
        command_type: CommandType
    ) -> CommandResult:
        """Execute a session command via CDP."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="",
                command=command_type,
                error="CDP adapter not available",
                session_id=session_id
            )

        start_time = datetime.utcnow()

        try:
            await self._ensure_connected()

            response = await self._send_cdp_command("Runtime.evaluate", {
                "expression": f"""
                if (window.cursor && window.cursor.{command}Session) {{
                    window.cursor.{command}Session('{session_id}')
                }} else {{
                    throw new Error('Cursor API not available');
                }}
                """
            })

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            if "result" in response and "exceptionDetails" not in response:
                result_value = response["result"].get("value", f"Session {command} completed")
                return CommandResult.create_success(
                    request_id="",
                    command=command_type,
                    output=str(result_value),
                    session_id=session_id,
                    duration_ms=duration_ms,
                    metadata=response
                )
            else:
                error_msg = response.get("exceptionDetails", {}).get("text", "Unknown error")
                return CommandResult.create_error(
                    request_id="",
                    command=command_type,
                    error=f"CDP error: {error_msg}",
                    session_id=session_id,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="",
                command=command_type,
                error=f"CDP error: {str(e)}",
                session_id=session_id,
                duration_ms=duration_ms
            )