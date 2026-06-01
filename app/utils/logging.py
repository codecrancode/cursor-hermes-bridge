"""Logging configuration and utilities."""

import json
import logging
import re
from typing import Any

from .config import settings


class SecretRedactingFormatter(logging.Formatter):
    """Formatter that redacts sensitive information from log messages."""

    # Patterns for sensitive data
    SECRET_PATTERNS = [
        (re.compile(r'("token":\s*")[^"]+(")', re.IGNORECASE), r'\1***REDACTED***\2'),
        (re.compile(r'("password":\s*")[^"]+(")', re.IGNORECASE), r'\1***REDACTED***\2'),
        (re.compile(r'("api_key":\s*")[^"]+(")', re.IGNORECASE), r'\1***REDACTED***\2'),
        (re.compile(r'("secret":\s*")[^"]+(")', re.IGNORECASE), r'\1***REDACTED***\2'),
        (re.compile(r'(token=)[^\s&]+', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(password=)[^\s&]+', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(api_key=)[^\s&]+', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(Authorization:\s*Bearer\s+)[^\s]+', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(Authorization:\s*Token\s+)[^\s]+', re.IGNORECASE), r'\1***REDACTED***'),
        # Telegram bot token pattern
        (re.compile(r'\b\d{8,10}:[A-Za-z0-9_-]{35}\b'), r'***REDACTED***'),
        # General token-like patterns (long alphanumeric strings)
        (re.compile(r'\b[A-Za-z0-9]{32,}\b'), r'***REDACTED***'),
    ]

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record, redacting sensitive information."""
        # Get the original formatted message
        original_message = super().format(record)

        # Apply redaction patterns
        redacted_message = original_message
        for pattern, replacement in self.SECRET_PATTERNS:
            redacted_message = pattern.sub(replacement, redacted_message)

        return redacted_message


class StructuredLogger:
    """Logger that provides structured logging capabilities."""

    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)

    def info(
        self,
        message: str,
        extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log info message with optional extra data."""
        self._log(logging.INFO, message, extra, **kwargs)

    def warning(
        self,
        message: str,
        extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log warning message with optional extra data."""
        self._log(logging.WARNING, message, extra, **kwargs)

    def error(
        self,
        message: str,
        extra: dict[str, Any] | None = None,
        exc_info: bool = True,
        **kwargs: Any,
    ) -> None:
        """Log error message with optional extra data."""
        self._log(logging.ERROR, message, extra, exc_info=exc_info, **kwargs)

    def debug(
        self,
        message: str,
        extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log debug message with optional extra data."""
        self._log(logging.DEBUG, message, extra, **kwargs)

    def critical(
        self,
        message: str,
        extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log critical message with optional extra data."""
        self._log(logging.CRITICAL, message, extra, **kwargs)

    def _log(
        self,
        level: int,
        message: str,
        extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Internal logging method that handles structured data."""
        if extra:
            # Add structured data to the message
            structured_data = json.dumps(extra, separators=(',', ':'))
            full_message = f"{message} | {structured_data}"
        else:
            full_message = message

        self.logger.log(level, full_message, **kwargs)


def setup_logging() -> None:
    """Set up application logging configuration."""
    # Set log level
    log_level = getattr(logging, settings.LOG_LEVEL.upper())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # Create formatter with secret redaction
    formatter = SecretRedactingFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)

    # Configure third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("watchdog").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


def redact_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Redact secrets from a dictionary."""
    redacted = data.copy()

    secret_keys = {
        "token", "password", "api_key", "secret", "authorization",
        "telegram_bot_token", "api_secret_token"
    }

    for key, value in redacted.items():
        if isinstance(key, str) and key.lower() in secret_keys:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, str):
            # Apply redaction patterns to string values
            for pattern, replacement in SecretRedactingFormatter.SECRET_PATTERNS:
                value = pattern.sub(replacement, value)
            redacted[key] = value
        elif isinstance(value, dict):
            redacted[key] = redact_secrets(value)

    return redacted


def log_config_on_startup() -> None:
    """Log sanitized configuration on application startup."""
    logger = get_logger("app.config")

    config_dict = {
        "api_host": settings.API_HOST,
        "api_port": settings.API_PORT,
        "database_path": settings.DATABASE_PATH,
        "adapter_primary": settings.ADAPTER_PRIMARY,
        "enable_cdp_adapter": settings.ENABLE_CDP_ADAPTER,
        "log_level": settings.LOG_LEVEL,
        "cursor_log_dir": settings.CURSOR_LOG_DIR,
        "cursor_session_dir": settings.CURSOR_SESSION_DIR,
        "allowed_chat_count": len(settings.TELEGRAM_ALLOWED_CHAT_IDS),
        "watch_paths_count": len(settings.WATCHER_LOG_PATHS),
    }

    logger.info("Application started with configuration", extra=config_dict)