"""Cursor CDP adapter — Chrome DevTools Protocol integration for Cursor IDE.

Proven approach:
- Discover Cursor's debug page via GET /json
- Connect via WebSocket to the main workbench page
- Read chat via Runtime.evaluate DOM queries
- Inject prompts via Input.insertText + Enter key
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

try:
    import httpx
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
    TimeoutError,
)

logger = get_logger("app.adapters.cursor_cdp")

# CDP discovery port (Cursor must be launched with --remote-debugging-port=9222)
CDP_PORT = 9222
DISCOVERY_TIMEOUT = 5.0


class CursorCDPAdapter(CursorAdapter):
    """Adapter using Chrome DevTools Protocol for Cursor integration.

    Connects to Cursor's Electron debug port, reads the chat DOM,
    and injects prompts via Input.insertText.
    """

    def __init__(self) -> None:
        self._page_ws_url: str | None = None
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
        return "Chrome DevTools Protocol — read & inject into Cursor chat"

    async def initialize(self) -> None:
        """Discover Cursor CDP endpoint and connect."""
        if self._initialized:
            return

        if not settings.ENABLE_CDP_ADAPTER:
            raise AdapterUnavailableError("CDP adapter is disabled by feature flag", self.name)

        if not WEBSOCKETS_AVAILABLE:
            raise AdapterUnavailableError("websockets library not available", self.name)

        logger.info("Discovering Cursor CDP endpoint on port %s...", CDP_PORT)

        self._page_ws_url = await self._discover_page()
        if not self._page_ws_url:
            raise AdapterUnavailableError(
                f"No Cursor debug page found on port {CDP_PORT}. "
                "Launch Cursor with: --remote-debugging-port=9222",
                self.name
            )

        try:
            await self._connect()
            await self._enable_domains()
            logger.info("CDP adapter connected to Cursor workbench")
        except Exception as e:
            raise AdapterUnavailableError(f"Failed to connect to CDP: {e}", self.name)

        self._initialized = True

    async def cleanup(self) -> None:
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            finally:
                self._websocket = None
        self._initialized = False

    def is_available(self) -> bool:
        return (
            settings.ENABLE_CDP_ADAPTER
            and WEBSOCKETS_AVAILABLE
            and self._page_ws_url is not None
        )

    def get_capabilities(self) -> dict[str, bool]:
        caps = super().get_capabilities()
        caps.update({
            "send_prompt": True,
            "read_chat": True,
            "new_session": True,
            "real_time_monitoring": True,
            "bidirectional_communication": True,
        })
        return caps

    # ── Public API ──────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        await self._ensure_connected()
        try:
            info = await self._evaluate("""
                JSON.stringify({
                    title: document.title,
                    url: window.location.href,
                    chatOpen: !!document.querySelector('.ProseMirror[contenteditable="true"]')
                })
            """)
            data = json.loads(info)
            return {
                "is_running": True,
                "title": data.get("title", ""),
                "chat_open": data.get("chatOpen", False),
                "adapter": self.name,
            }
        except Exception as e:
            return {"is_running": True, "adapter": self.name, "error": str(e)}

    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult:
        """Inject a prompt into Cursor's chat input and submit it."""
        if not self.is_available():
            return CommandResult.create_error(
                request_id="", command=CommandType.SEND,
                error="CDP adapter not available", session_id=session_id
            )

        start_time = datetime.utcnow()
        try:
            await self._ensure_connected()

            # Focus and clear the ProseMirror editor
            editor_info = await self._evaluate("""
                (function() {
                    let editor = document.querySelector('.ProseMirror[contenteditable="true"]');
                    if (!editor) editor = document.querySelector('[contenteditable="true"]');
                    if (editor) {
                        editor.focus();
                        document.execCommand('selectAll');
                        return JSON.stringify({found: true, tag: editor.tagName});
                    }
                    return JSON.stringify({found: false});
                })()
            """)

            if '"found":false' in editor_info:
                return CommandResult.create_error(
                    request_id="", command=CommandType.SEND,
                    error="Could not find Cursor chat input — is a chat open?",
                    session_id=session_id
                )

            # Insert text using the reliable CDP method
            await self._send_cdp("Input.insertText", {"text": prompt})
            await asyncio.sleep(0.05)

            # Submit with Enter
            await self._send_cdp("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13,
            })
            await self._send_cdp("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13,
            })

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_success(
                request_id="", command=CommandType.SEND,
                output=f"Prompt sent: {prompt[:80]}...",
                session_id=session_id, duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return CommandResult.create_error(
                request_id="", command=CommandType.SEND,
                error=f"CDP error: {e}", session_id=session_id,
                duration_ms=duration_ms,
            )

    async def read_chat(self, max_messages: int = 5) -> list[dict[str, str]]:
        """Read recent chat messages from Cursor's DOM."""
        await self._ensure_connected()

        result = await self._evaluate(f"""
            (function() {{
                let messages = [];
                let humanMsgs = document.querySelectorAll('.composer-human-message-content');
                humanMsgs.forEach(el => {{
                    let text = el.innerText ? el.innerText.trim() : '';
                    if (text.length > 0) {{
                        messages.push({{role: 'user', text: text.substring(0, 500)}});
                    }}
                }});
                return JSON.stringify(messages.slice(-{max_messages}));
            }})()
        """)
        return json.loads(result)

    async def new_session(self, name: str | None = None) -> CommandResult:
        """Create a new Cursor agent session (Ctrl+N)."""
        await self._ensure_connected()
        await self._send_cdp("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": "n", "code": "KeyN",
            "modifiers": 2, "windowsVirtualKeyCode": 78,
        })
        await self._send_cdp("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "n", "code": "KeyN",
            "modifiers": 2, "windowsVirtualKeyCode": 78,
        })
        return CommandResult.create_success(
            request_id="", command=CommandType.NEW,
            output="New agent session created (Ctrl+N)",
        )

    async def list_sessions(self) -> list[Session]:
        """List sessions visible in Cursor's sidebar (read-only via DOM)."""
        try:
            await self._ensure_connected()
            raw = await self._evaluate("""
                (function() {
                    let items = document.querySelectorAll('[class*="chat-title"], [class*="session-item"]');
                    let names = [];
                    items.forEach(el => { names.push(el.innerText.trim().substring(0, 100)); });
                    return JSON.stringify(names.slice(0, 20));
                })()
            """)
            names = json.loads(raw)
            return [
                Session(
                    id=f"cursor-{i}",
                    name=name or "Unknown",
                    status=SessionStatus("idle"),
                    adapter=self.name,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                for i, name in enumerate(names)
            ]
        except Exception:
            return []

    async def continue_session(self, session_id: str) -> CommandResult:
        return CommandResult.create_success(
            request_id="", command=CommandType.CONTINUE,
            output="Continue not supported via CDP", session_id=session_id,
        )

    async def stop_session(self, session_id: str) -> CommandResult:
        return CommandResult.create_success(
            request_id="", command=CommandType.STOP,
            output="Stop not supported via CDP", session_id=session_id,
        )

    async def switch_session(self, session_id: str) -> CommandResult:
        return CommandResult.create_success(
            request_id="", command=CommandType.SWITCH,
            output="Switch not supported via CDP", session_id=session_id,
        )

    async def get_session_summary(self, session_id: str) -> str:
        try:
            await self._ensure_connected()
            return await self._evaluate("document.body.innerText.substring(0, 2000)")
        except Exception as e:
            return f"CDP error: {e}"

    async def tail_session(self, session_id: str, lines: int = 20) -> str:
        return await self.get_session_summary(session_id)

    async def get_progress(self, session_id: str) -> list[ProgressEvent]:
        return []

    async def get_workspace_info(self) -> dict[str, Any]:
        try:
            await self._ensure_connected()
            raw = await self._evaluate("""
                JSON.stringify({
                    title: document.title,
                    visibleProjects: Array.from(
                        document.querySelectorAll('[class*="project"], [class*="workspace"]')
                    ).slice(0, 5).map(el => el.innerText.trim().substring(0, 60))
                })
            """)
            return json.loads(raw)
        except Exception as e:
            return {"error": str(e)}

    # ── Internal Helpers ────────────────────────────────────────

    async def _discover_page(self) -> str | None:
        """Hit /json to find the main Cursor workbench page."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://localhost:{CDP_PORT}/json",
                    timeout=DISCOVERY_TIMEOUT,
                )
                resp.raise_for_status()
                pages = resp.json()

            for page in pages:
                if page.get("type") == "page" and "Cursor" in page.get("title", ""):
                    ws_url = page.get("webSocketDebuggerUrl")
                    logger.info("Found Cursor page: %s", page.get("title"))
                    return ws_url

            logger.warning("No Cursor page found in /json targets")
            return None
        except Exception as e:
            logger.warning("CDP discovery failed: %s", e)
            return None

    async def _connect(self) -> None:
        if not self._page_ws_url:
            raise CommunicationError("No CDP page URL", self.name)
        try:
            self._websocket = await asyncio.wait_for(
                websockets.connect(self._page_ws_url),
                timeout=self._connection_timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"CDP connect timeout ({self._connection_timeout}s)", self.name)

    async def _enable_domains(self) -> None:
        """Enable Runtime and Input domains."""
        await self._send_cdp("Runtime.enable")
        await self._send_cdp("Input.enable")

    async def _ensure_connected(self) -> None:
        if not self._websocket or self._websocket.closed:
            await self._connect()
            await self._enable_domains()

    async def _send_cdp(self, method: str, params: dict | None = None) -> dict:
        """Send a CDP command and return the response."""
        self._message_id += 1
        msg = {"id": self._message_id, "method": method, "params": params or {}}
        await self._websocket.send(json.dumps(msg))

        while True:
            raw = await asyncio.wait_for(
                self._websocket.recv(), timeout=self._command_timeout
            )
            resp = json.loads(raw)
            if resp.get("id") == self._message_id:
                return resp

    async def _evaluate(self, expression: str) -> str:
        """Run a JS expression and return the result value as a string."""
        resp = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        result = resp.get("result", {}).get("result", {})
        return result.get("value", "")
