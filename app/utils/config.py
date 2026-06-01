"""Configuration management using Pydantic Settings."""

import os
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=True,
    )

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram bot token")
    TELEGRAM_ALLOWED_CHAT_IDS: list[int] = Field(
        default_factory=list, description="List of allowed chat IDs"
    )

    # API Configuration
    API_HOST: str = Field(default="127.0.0.1", description="API host address")
    API_PORT: int = Field(default=8920, description="API port")
    API_SECRET_TOKEN: str = Field(
        default="", description="API secret token (empty = localhost-only)"
    )

    # Storage Configuration
    DATABASE_PATH: str = Field(
        default="data/cursor-bridge.db", description="SQLite database path"
    )
    JSONL_EXPORT_PATH: str = Field(
        default="", description="JSONL export path (empty = disabled)"
    )

    # Watcher Configuration
    WATCHER_LOG_PATHS: list[str] = Field(
        default_factory=list, description="Additional log paths to watch"
    )

    # Adapter Configuration
    ADAPTER_PRIMARY: str = Field(
        default="cursor_logs", description="Primary adapter to use"
    )
    ENABLE_CDP_ADAPTER: bool = Field(
        default=False, description="Enable Chrome DevTools Protocol adapter"
    )

    # Summarizer Configuration
    SUMMARIZER_TYPE: str = Field(
        default="local", description="Summarizer type to use"
    )

    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Platform-specific Cursor paths
    CURSOR_LOG_DIR: str = Field(
        default_factory=lambda: _get_default_cursor_log_dir(),
        description="Cursor logs directory",
    )
    CURSOR_SESSION_DIR: str = Field(
        default_factory=lambda: _get_default_cursor_session_dir(),
        description="Cursor sessions directory",
    )

    # Service Configuration
    PROGRESS_INACTIVITY_TIMEOUT_MINUTES: int = Field(
        default=30, description="Inactivity timeout in minutes"
    )
    TELEGRAM_RETRY_MAX_ATTEMPTS: int = Field(
        default=3, description="Maximum retry attempts for Telegram API"
    )
    TELEGRAM_RETRY_DELAY_SECONDS: int = Field(
        default=1, description="Initial retry delay in seconds"
    )

    @field_validator("TELEGRAM_ALLOWED_CHAT_IDS", mode="before")
    @classmethod
    def parse_chat_ids(cls, v: Any) -> list[int]:
        """Parse chat IDs from various formats."""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                # Parse list format: [123,456,789]
                v = v[1:-1]
            if v:
                return [int(x.strip()) for x in v.split(",") if x.strip()]
            return []
        elif isinstance(v, list):
            return [int(x) for x in v]
        elif isinstance(v, int):
            return [v]
        return []

    @field_validator("WATCHER_LOG_PATHS", mode="before")
    @classmethod
    def parse_log_paths(cls, v: Any) -> list[str]:
        """Parse log paths from various formats."""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                # Parse list format: [path1,path2,path3]
                v = v[1:-1]
            if v:
                return [x.strip() for x in v.split(",") if x.strip()]
            return []
        elif isinstance(v, list):
            return v
        return []

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v

    @field_validator("ADAPTER_PRIMARY")
    @classmethod
    def validate_adapter(cls, v: str) -> str:
        """Validate adapter name."""
        valid_adapters = {"cursor_logs", "cursor_cli", "cursor_cdp"}
        if v not in valid_adapters:
            raise ValueError(f"Invalid adapter: {v}")
        return v

    def get_cursor_log_paths(self) -> list[str]:
        """Get all cursor log paths to watch."""
        paths = []

        # Add default cursor log directory if it exists
        if os.path.exists(self.CURSOR_LOG_DIR):
            paths.append(self.CURSOR_LOG_DIR)

        # Add default cursor session directory if it exists
        if os.path.exists(self.CURSOR_SESSION_DIR):
            paths.append(self.CURSOR_SESSION_DIR)

        # Add additional watcher paths
        for path in self.WATCHER_LOG_PATHS:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path):
                paths.append(expanded_path)

        return paths

    def is_localhost_only(self) -> bool:
        """Check if API is configured for localhost only."""
        return not self.API_SECRET_TOKEN

    def should_export_jsonl(self) -> bool:
        """Check if JSONL export is enabled."""
        return bool(self.JSONL_EXPORT_PATH)


def _get_default_cursor_log_dir() -> str:
    """Get the default Cursor log directory for the current platform."""
    if os.name == "nt":  # Windows
        app_data = os.environ.get("APPDATA", "")
        return os.path.join(app_data, "Cursor", "logs")
    elif os.name == "posix":
        if os.uname().sysname == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Application Support/Cursor/logs")
        else:  # Linux
            return os.path.expanduser("~/.config/Cursor/logs")
    return ""


def _get_default_cursor_session_dir() -> str:
    """Get the default Cursor session directory for the current platform."""
    if os.name == "nt":  # Windows
        app_data = os.environ.get("APPDATA", "")
        return os.path.join(app_data, "Cursor", "sessions")
    elif os.name == "posix":
        if os.uname().sysname == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Application Support/Cursor/sessions")
        else:  # Linux
            return os.path.expanduser("~/.config/Cursor/sessions")
    return ""


# Global settings instance
settings = Settings()