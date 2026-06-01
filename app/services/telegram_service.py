"""Telegram bot service."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..adapters.base import adapter_registry
from ..models.alert import Alert
from ..models.command_request import CommandRequest, CommandType
from ..models.session import SessionStatus
from ..utils.config import settings
from ..utils.logging import get_logger

logger = get_logger("app.services.telegram_service")


class TelegramService:
    """Service for managing Telegram bot interactions."""

    def __init__(
        self,
        auth_service: Any,
        session_service: Any,
        progress_service: Any,
        summary_service: Any
    ) -> None:
        self.auth_service = auth_service
        self.session_service = session_service
        self.progress_service = progress_service
        self.summary_service = summary_service

        self.bot: Bot | None = None
        self.dispatcher: Dispatcher | None = None
        self._running = False
        self._retry_delay = settings.TELEGRAM_RETRY_DELAY_SECONDS
        self._max_retries = settings.TELEGRAM_RETRY_MAX_ATTEMPTS

    async def initialize(self) -> None:
        """Initialize the Telegram bot and dispatcher."""
        if self._running:
            return

        logger.info("Initializing Telegram service")

        # Initialize bot
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.dispatcher = Dispatcher()

        # Register handlers
        self._register_handlers()

        # Test connection
        try:
            bot_info = await self.bot.get_me()
            logger.info("Telegram bot initialized", extra={
                "bot_id": bot_info.id,
                "bot_username": bot_info.username,
                "bot_name": bot_info.first_name
            })
        except Exception as e:
            logger.error("Failed to initialize Telegram bot", extra={"error": str(e)})
            raise

        self._running = True

    async def start_polling(self) -> None:
        """Start the Telegram bot polling loop."""
        if not self.dispatcher or not self.bot:
            raise RuntimeError("Telegram service not initialized")

        logger.info("Starting Telegram bot polling")
        try:
            await self.dispatcher.start_polling(self.bot)
        except Exception as e:
            logger.error("Error in Telegram polling", extra={"error": str(e)})
            raise

    async def stop(self) -> None:
        """Stop the Telegram service."""
        if not self._running:
            return

        logger.info("Stopping Telegram service")

        if self.dispatcher:
            await self.dispatcher.stop_polling()

        if self.bot:
            await self.bot.session.close()

        self._running = False

    def _register_handlers(self) -> None:
        """Register message handlers for bot commands."""
        if not self.dispatcher:
            return

        # Command handlers
        self.dispatcher.message.register(self._handle_start, CommandStart())
        self.dispatcher.message.register(self._handle_status, Command("status"))
        self.dispatcher.message.register(self._handle_send, Command("send"))
        self.dispatcher.message.register(self._handle_continue, Command("continue"))
        self.dispatcher.message.register(self._handle_stop, Command("stop"))
        self.dispatcher.message.register(self._handle_new, Command("new"))
        self.dispatcher.message.register(self._handle_sessions, Command("sessions"))
        self.dispatcher.message.register(self._handle_switch, Command("switch"))
        self.dispatcher.message.register(self._handle_summary, Command("summary"))
        self.dispatcher.message.register(self._handle_tail, Command("tail"))
        self.dispatcher.message.register(self._handle_help, Command("help"))

        # Fallback handler for unauthorized messages
        self.dispatcher.message.register(self._handle_unauthorized)

    async def _handle_start(self, message: Message) -> None:
        """Handle /start command."""
        if not await self._check_authorization(message):
            return

        welcome_text = (
            "🤖 Welcome to Cursor-Hermes Bridge!\n\n"
            "Available commands:\n"
            "/status - Show Cursor status\n"
            "/send <prompt> - Send prompt to active session\n"
            "/continue - Continue current session\n"
            "/stop - Stop current session\n"
            "/new - Start a new session\n"
            "/sessions - List recent sessions\n"
            "/switch <id> - Switch to a different session\n"
            "/summary - Get summary of active session\n"
            "/tail [lines] - Show recent output\n"
            "/help - Show this help message"
        )

        await self._send_message(message.chat.id, welcome_text)

    async def _handle_status(self, message: Message) -> None:
        """Handle /status command."""
        if not await self._check_authorization(message):
            return

        try:
            # Get primary adapter status
            adapter = adapter_registry.get_primary()
            if not adapter:
                await self._send_message(message.chat.id, "❌ No adapter available")
                return

            status = await adapter.get_status()
            active_session = await self.session_service.get_active_session()

            # Get recent progress events if there's an active session
            recent_events = []
            if active_session:
                recent_events = await self.progress_service.get_recent_progress_events(
                    active_session.id, 30
                )

            # Generate status message
            status_text = await self.summary_service.generate_status_message(
                active_session, recent_events
            )

            # Add adapter info
            status_text += f"\n\nAdapter: {adapter.name}"
            if status.get("workspace"):
                status_text += f"\nWorkspace: {status['workspace']}"

            await self._send_message(message.chat.id, status_text)

        except Exception as e:
            logger.error("Error handling status command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error getting status: {str(e)}")

    async def _handle_send(self, message: Message) -> None:
        """Handle /send command."""
        if not await self._check_authorization(message):
            return

        # Extract prompt from command
        command_parts = message.text.split(" ", 1)
        if len(command_parts) < 2:
            await self._send_message(message.chat.id, "❌ Please provide a prompt: /send <prompt>")
            return

        prompt = command_parts[1]

        try:
            # Get active session
            active_session = await self.session_service.get_active_session()
            if not active_session:
                await self._send_message(message.chat.id, "❌ No active session. Use /new to start one.")
                return

            # Get adapter
            adapter = await self.session_service.get_session_adapter(active_session.id)
            if not adapter:
                await self._send_message(message.chat.id, "❌ Session adapter not available")
                return

            # Send prompt
            result = await adapter.send_prompt(active_session.id, prompt)

            if result.is_success():
                response_text = f"✅ Prompt sent to session '{active_session.name}'"
                if result.output:
                    response_text += f"\n\nResponse: {result.output}"
            else:
                response_text = f"❌ Failed to send prompt: {result.error}"

            await self._send_message(message.chat.id, response_text)

        except Exception as e:
            logger.error("Error handling send command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error sending prompt: {str(e)}")

    async def _handle_continue(self, message: Message) -> None:
        """Handle /continue command."""
        if not await self._check_authorization(message):
            return

        try:
            active_session = await self.session_service.get_active_session()
            if not active_session:
                await self._send_message(message.chat.id, "❌ No active session to continue")
                return

            adapter = await self.session_service.get_session_adapter(active_session.id)
            if not adapter:
                await self._send_message(message.chat.id, "❌ Session adapter not available")
                return

            result = await adapter.continue_session(active_session.id)

            if result.is_success():
                response_text = f"▶️ Continued session '{active_session.name}'"
                if result.output:
                    response_text += f"\n\n{result.output}"
            else:
                response_text = f"❌ Failed to continue session: {result.error}"

            await self._send_message(message.chat.id, response_text)

        except Exception as e:
            logger.error("Error handling continue command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error continuing session: {str(e)}")

    async def _handle_stop(self, message: Message) -> None:
        """Handle /stop command."""
        if not await self._check_authorization(message):
            return

        try:
            active_session = await self.session_service.get_active_session()
            if not active_session:
                await self._send_message(message.chat.id, "❌ No active session to stop")
                return

            adapter = await self.session_service.get_session_adapter(active_session.id)
            if not adapter:
                await self._send_message(message.chat.id, "❌ Session adapter not available")
                return

            result = await adapter.stop_session(active_session.id)

            if result.is_success():
                # Update session status
                await self.session_service.update_session_status(
                    active_session.id, SessionStatus.PAUSED
                )
                response_text = f"⏹️ Stopped session '{active_session.name}'"
                if result.output:
                    response_text += f"\n\n{result.output}"
            else:
                response_text = f"❌ Failed to stop session: {result.error}"

            await self._send_message(message.chat.id, response_text)

        except Exception as e:
            logger.error("Error handling stop command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error stopping session: {str(e)}")

    async def _handle_new(self, message: Message) -> None:
        """Handle /new command."""
        if not await self._check_authorization(message):
            return

        # Extract optional session name
        command_parts = message.text.split(" ", 1)
        session_name = command_parts[1] if len(command_parts) > 1 else None

        try:
            # Get primary adapter
            adapter = adapter_registry.get_primary()
            if not adapter:
                await self._send_message(message.chat.id, "❌ No adapter available")
                return

            # Create session via adapter if supported
            if adapter.get_capabilities().get("new_session", False):
                result = await adapter.new_session(session_name)
                if result.is_success():
                    # Session created via adapter
                    response_text = f"✨ Created new session"
                    if result.output:
                        response_text += f": {result.output}"
                else:
                    await self._send_message(message.chat.id, f"❌ Failed to create session: {result.error}")
                    return
            else:
                # Create session locally
                if not session_name:
                    session_name = f"Session {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

                session = await self.session_service.create_session(
                    name=session_name,
                    adapter_name=adapter.name
                )

                # Set as active
                await self.session_service.set_active_session(session.id)

                response_text = f"✨ Created new session '{session.name}'"

            await self._send_message(message.chat.id, response_text)

        except Exception as e:
            logger.error("Error handling new command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error creating session: {str(e)}")

    async def _handle_sessions(self, message: Message) -> None:
        """Handle /sessions command."""
        if not await self._check_authorization(message):
            return

        try:
            sessions = await self.session_service.list_sessions(limit=10)
            sessions_text = await self.summary_service.format_session_list(sessions)
            await self._send_message(message.chat.id, sessions_text)

        except Exception as e:
            logger.error("Error handling sessions command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error listing sessions: {str(e)}")

    async def _handle_switch(self, message: Message) -> None:
        """Handle /switch command."""
        if not await self._check_authorization(message):
            return

        # Extract session ID
        command_parts = message.text.split(" ", 1)
        if len(command_parts) < 2:
            await self._send_message(message.chat.id, "❌ Please provide session ID: /switch <session_id>")
            return

        session_id = command_parts[1].strip()

        try:
            # Check if session exists
            session = await self.session_service.get_session(session_id)
            if not session:
                await self._send_message(message.chat.id, f"❌ Session '{session_id}' not found")
                return

            # Try to switch via adapter first
            adapter = await self.session_service.get_session_adapter(session_id)
            if adapter and adapter.get_capabilities().get("switch_session", False):
                result = await adapter.switch_session(session_id)
                if not result.is_success():
                    await self._send_message(message.chat.id, f"❌ Failed to switch session: {result.error}")
                    return

            # Set as active locally
            success = await self.session_service.set_active_session(session_id)
            if success:
                await self._send_message(message.chat.id, f"🔀 Switched to session '{session.name}'")
            else:
                await self._send_message(message.chat.id, f"❌ Failed to switch to session '{session_id}'")

        except Exception as e:
            logger.error("Error handling switch command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error switching session: {str(e)}")

    async def _handle_summary(self, message: Message) -> None:
        """Handle /summary command."""
        if not await self._check_authorization(message):
            return

        try:
            active_session = await self.session_service.get_active_session()
            if not active_session:
                await self._send_message(message.chat.id, "❌ No active session")
                return

            # Get progress events
            events = await self.progress_service.get_progress_events(active_session.id, limit=50)

            # Generate summary
            summary = await self.summary_service.summarize_session(active_session, events)

            await self._send_message(message.chat.id, summary)

        except Exception as e:
            logger.error("Error handling summary command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error getting summary: {str(e)}")

    async def _handle_tail(self, message: Message) -> None:
        """Handle /tail command."""
        if not await self._check_authorization(message):
            return

        # Extract optional line count
        command_parts = message.text.split(" ")
        lines = 20  # default
        if len(command_parts) > 1:
            try:
                lines = int(command_parts[1])
                lines = max(1, min(lines, 100))  # Clamp between 1 and 100
            except ValueError:
                await self._send_message(message.chat.id, "❌ Invalid line count. Using default (20).")

        try:
            active_session = await self.session_service.get_active_session()
            if not active_session:
                await self._send_message(message.chat.id, "❌ No active session")
                return

            adapter = await self.session_service.get_session_adapter(active_session.id)
            if not adapter:
                await self._send_message(message.chat.id, "❌ Session adapter not available")
                return

            tail_output = await adapter.tail_session(active_session.id, lines)

            if tail_output:
                # Truncate if too long for Telegram
                if len(tail_output) > 4000:
                    tail_output = tail_output[-4000:] + "\n... (truncated)"

                response_text = f"📋 Last {lines} lines from '{active_session.name}':\n\n```\n{tail_output}\n```"
            else:
                response_text = f"📋 No output available for session '{active_session.name}'"

            await self._send_message(message.chat.id, response_text, parse_mode="Markdown")

        except Exception as e:
            logger.error("Error handling tail command", extra={"error": str(e)})
            await self._send_message(message.chat.id, f"❌ Error getting tail: {str(e)}")

    async def _handle_help(self, message: Message) -> None:
        """Handle /help command."""
        if not await self._check_authorization(message):
            return

        help_text = (
            "🤖 Cursor-Hermes Bridge Commands\n\n"
            "📊 **Status & Info**\n"
            "/status - Show current Cursor status\n"
            "/sessions - List recent sessions\n"
            "/summary - Get summary of active session\n"
            "/tail [lines] - Show recent output (default: 20 lines)\n\n"
            "🎮 **Session Control**\n"
            "/send <prompt> - Send prompt to active session\n"
            "/continue - Continue current session\n"
            "/stop - Stop current session\n"
            "/new [name] - Start a new session\n"
            "/switch <id> - Switch to a different session\n\n"
            "❓ **Help**\n"
            "/help - Show this help message"
        )

        await self._send_message(message.chat.id, help_text, parse_mode="Markdown")

    async def _handle_unauthorized(self, message: Message) -> None:
        """Handle messages from unauthorized chats."""
        # This will only be reached if authorization check passes,
        # so this is for unknown commands
        if await self._check_authorization(message):
            await self._send_message(
                message.chat.id,
                "❓ Unknown command. Use /help to see available commands."
            )

    async def _check_authorization(self, message: Message) -> bool:
        """Check if a message is from an authorized chat."""
        authorized = await self.auth_service.validate_telegram_message(
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else None,
            username=message.from_user.username if message.from_user else None,
            command=message.text.split()[0] if message.text else None,
            message=message.text
        )

        if not authorized:
            await self._send_message(
                message.chat.id,
                "🚫 Unauthorized. This bot is private."
            )

        return authorized

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None
    ) -> bool:
        """Send a message with retry logic.

        Args:
            chat_id: The chat ID to send to
            text: The message text
            parse_mode: Optional parse mode (Markdown, HTML)
            reply_to_message_id: Optional message to reply to

        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.bot:
            return False

        for attempt in range(self._max_retries):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id
                )
                return True

            except TelegramAPIError as e:
                logger.warning("Telegram API error", extra={
                    "chat_id": chat_id,
                    "attempt": attempt + 1,
                    "error": str(e)
                })

                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.error("Failed to send message after retries", extra={
                        "chat_id": chat_id,
                        "max_retries": self._max_retries
                    })

            except Exception as e:
                logger.error("Unexpected error sending message", extra={
                    "chat_id": chat_id,
                    "attempt": attempt + 1,
                    "error": str(e)
                })
                break

        return False

    async def send_alert_notification(self, alert: Alert) -> bool:
        """Send an alert notification to all authorized chats.

        Args:
            alert: The alert to send

        Returns:
            True if sent to at least one chat, False otherwise
        """
        if not alert.requires_attention():
            return True  # Skip non-critical alerts

        # Get session info if available
        session = None
        if alert.session_id:
            session = await self.session_service.get_session(alert.session_id)

        # Generate appropriate message based on alert type
        if alert.type.value == "task_complete" and session:
            from ..models.progress_event import ProgressEvent
            # Create a mock completion event for the message
            completion_event = ProgressEvent.create_new(
                session_id=alert.session_id,
                stage="completed",
                detail=alert.message
            )
            message_text = await self.summary_service.generate_completion_message(
                session, completion_event
            )
        elif alert.type.value == "task_error" and session:
            from ..models.progress_event import ProgressEvent
            # Create a mock error event for the message
            error_event = ProgressEvent.create_new(
                session_id=alert.session_id,
                stage="error",
                detail=alert.message
            )
            message_text = await self.summary_service.generate_error_message(
                session, error_event
            )
        elif alert.type.value == "approval_needed" and session:
            from ..models.progress_event import ProgressEvent
            # Create a mock approval event for the message
            approval_event = ProgressEvent.create_new(
                session_id=alert.session_id,
                stage="approval",
                detail=alert.message
            )
            message_text = await self.summary_service.generate_approval_message(
                session, approval_event
            )
        else:
            # Generic alert message
            severity_emoji = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌",
                "critical": "🚨"
            }.get(alert.severity.value, "📢")

            message_text = f"{severity_emoji} {alert.message}"
            if session:
                message_text += f"\nSession: {session.name}"

        # Send to all authorized chats
        authorized_chats = await self.auth_service.list_authorized_chats()
        success_count = 0

        for chat_info in authorized_chats:
            chat_id = chat_info["chat_id"]
            success = await self._send_message(chat_id, message_text)
            if success:
                success_count += 1

        logger.info("Sent alert notification", extra={
            "alert_id": alert.id,
            "alert_type": alert.type.value,
            "chats_sent": success_count,
            "total_chats": len(authorized_chats)
        })

        return success_count > 0

    async def get_service_info(self) -> dict[str, Any]:
        """Get information about the Telegram service.

        Returns:
            Dictionary with service information
        """
        info = {
            "running": self._running,
            "bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "retry_settings": {
                "max_retries": self._max_retries,
                "retry_delay": self._retry_delay
            }
        }

        if self.bot and self._running:
            try:
                bot_info = await self.bot.get_me()
                info["bot_info"] = {
                    "id": bot_info.id,
                    "username": bot_info.username,
                    "first_name": bot_info.first_name,
                    "can_join_groups": bot_info.can_join_groups,
                    "can_read_all_group_messages": bot_info.can_read_all_group_messages,
                    "supports_inline_queries": bot_info.supports_inline_queries
                }
            except Exception as e:
                info["bot_info_error"] = str(e)

        return info