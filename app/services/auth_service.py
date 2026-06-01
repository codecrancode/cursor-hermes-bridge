"""Authentication and authorization service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..storage.database import Database
from ..utils.config import settings
from ..utils.logging import get_logger

logger = get_logger("app.services.auth_service")


class AuthService:
    """Service for handling authentication and authorization."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the auth service and sync configured chat IDs."""
        if self._initialized:
            return

        logger.info("Initializing auth service")

        # Add configured chat IDs to the database
        for chat_id in settings.TELEGRAM_ALLOWED_CHAT_IDS:
            try:
                await self.database.add_authorized_chat(
                    chat_id=chat_id,
                    name=f"Configured chat {chat_id}"
                )
                logger.debug("Added configured chat ID", extra={"chat_id": chat_id})
            except Exception as e:
                logger.error("Error adding configured chat ID", extra={
                    "chat_id": chat_id,
                    "error": str(e)
                })

        self._initialized = True
        logger.info("Auth service initialized", extra={
            "configured_chats": len(settings.TELEGRAM_ALLOWED_CHAT_IDS)
        })

    async def is_chat_authorized(self, chat_id: int) -> bool:
        """Check if a chat is authorized to use the bot.

        Args:
            chat_id: The Telegram chat ID to check

        Returns:
            True if the chat is authorized, False otherwise
        """
        # First check configured list (fast path)
        if chat_id in settings.TELEGRAM_ALLOWED_CHAT_IDS:
            return True

        # Then check database
        try:
            authorized = await self.database.is_chat_authorized(chat_id)
            if authorized:
                logger.debug("Chat authorized via database", extra={"chat_id": chat_id})
            return authorized
        except Exception as e:
            logger.error("Error checking chat authorization", extra={
                "chat_id": chat_id,
                "error": str(e)
            })
            # Fall back to configured list only
            return False

    async def log_unauthorized_access(
        self,
        chat_id: int,
        user_id: int | None = None,
        username: str | None = None,
        command: str | None = None,
        message: str | None = None
    ) -> None:
        """Log an unauthorized access attempt.

        Args:
            chat_id: The chat ID that attempted access
            user_id: The user ID (if available)
            username: The username (if available)
            command: The command that was attempted
            message: The message content (truncated)
        """
        # Truncate message for logging
        truncated_message = None
        if message:
            truncated_message = message[:100] + "..." if len(message) > 100 else message

        logger.warning("Unauthorized access attempt", extra={
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "command": command,
            "message": truncated_message,
            "timestamp": datetime.utcnow().isoformat()
        })

        # TODO: Consider storing unauthorized attempts in database for analysis

    async def authorize_chat(
        self,
        chat_id: int,
        name: str | None = None,
        authorized_by: str | None = None
    ) -> bool:
        """Authorize a new chat to use the bot.

        Args:
            chat_id: The chat ID to authorize
            name: Optional name/description for the chat
            authorized_by: Who authorized this chat

        Returns:
            True if successfully authorized, False otherwise
        """
        try:
            await self.database.add_authorized_chat(
                chat_id=chat_id,
                name=name or f"Chat {chat_id}"
            )

            logger.info("Authorized new chat", extra={
                "chat_id": chat_id,
                "name": name,
                "authorized_by": authorized_by
            })
            return True

        except Exception as e:
            logger.error("Error authorizing chat", extra={
                "chat_id": chat_id,
                "error": str(e)
            })
            return False

    async def deauthorize_chat(self, chat_id: int) -> bool:
        """Remove authorization for a chat.

        Args:
            chat_id: The chat ID to deauthorize

        Returns:
            True if successfully deauthorized, False if not found
        """
        try:
            success = await self.database.remove_authorized_chat(chat_id)
            if success:
                logger.info("Deauthorized chat", extra={"chat_id": chat_id})
            else:
                logger.warning("Attempted to deauthorize non-existent chat", extra={
                    "chat_id": chat_id
                })
            return success

        except Exception as e:
            logger.error("Error deauthorizing chat", extra={
                "chat_id": chat_id,
                "error": str(e)
            })
            return False

    async def list_authorized_chats(self) -> list[dict[str, Any]]:
        """Get a list of all authorized chats.

        Returns:
            List of authorized chat information
        """
        try:
            # Get chats from database
            db_chats = await self.database.list_authorized_chats()

            # Combine with configured chats
            configured_chats = set(settings.TELEGRAM_ALLOWED_CHAT_IDS)
            db_chat_ids = {chat["chat_id"] for chat in db_chats}

            # Add configured chats that aren't in the database
            all_chats = list(db_chats)
            for chat_id in configured_chats:
                if chat_id not in db_chat_ids:
                    all_chats.append({
                        "chat_id": chat_id,
                        "name": f"Configured chat {chat_id}",
                        "added_at": "configuration",
                        "source": "config"
                    })

            # Mark sources for existing chats
            for chat in all_chats:
                if "source" not in chat:
                    chat["source"] = "database"
                    if chat["chat_id"] in configured_chats:
                        chat["source"] = "both"

            return all_chats

        except Exception as e:
            logger.error("Error listing authorized chats", extra={"error": str(e)})
            return []

    async def get_authorization_stats(self) -> dict[str, Any]:
        """Get statistics about authorization.

        Returns:
            Dictionary with authorization statistics
        """
        try:
            authorized_chats = await self.list_authorized_chats()

            stats = {
                "total_authorized_chats": len(authorized_chats),
                "configured_chats": len(settings.TELEGRAM_ALLOWED_CHAT_IDS),
                "database_chats": len([c for c in authorized_chats if c.get("source") in ["database", "both"]]),
                "config_only_chats": len([c for c in authorized_chats if c.get("source") == "config"]),
                "both_sources_chats": len([c for c in authorized_chats if c.get("source") == "both"]),
            }

            return stats

        except Exception as e:
            logger.error("Error getting authorization stats", extra={"error": str(e)})
            return {}

    def check_api_authorization(self, token: str | None) -> bool:
        """Check if an API request is authorized.

        Args:
            token: The provided API token

        Returns:
            True if authorized, False otherwise
        """
        # If no secret token is configured, allow localhost-only access
        if not settings.API_SECRET_TOKEN:
            return True  # Assuming this is called only for localhost requests

        # Check if the provided token matches the configured secret
        return token == settings.API_SECRET_TOKEN

    def is_localhost_only(self) -> bool:
        """Check if API is configured for localhost-only access.

        Returns:
            True if API is localhost-only (no secret token configured)
        """
        return not settings.API_SECRET_TOKEN

    async def validate_telegram_message(
        self,
        chat_id: int,
        user_id: int | None = None,
        username: str | None = None,
        command: str | None = None,
        message: str | None = None
    ) -> bool:
        """Validate a Telegram message for authorization.

        Args:
            chat_id: The chat ID
            user_id: The user ID (if available)
            username: The username (if available)
            command: The command being executed
            message: The message content

        Returns:
            True if authorized, False otherwise
        """
        authorized = await self.is_chat_authorized(chat_id)

        if not authorized:
            await self.log_unauthorized_access(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                command=command,
                message=message
            )

        return authorized

    async def get_security_info(self) -> dict[str, Any]:
        """Get security configuration information.

        Returns:
            Dictionary with security information (no sensitive data)
        """
        auth_stats = await self.get_authorization_stats()

        return {
            "telegram_auth_enabled": len(settings.TELEGRAM_ALLOWED_CHAT_IDS) > 0,
            "api_secret_configured": bool(settings.API_SECRET_TOKEN),
            "localhost_only": self.is_localhost_only(),
            "authorization_stats": auth_stats,
            "initialized": self._initialized,
        }