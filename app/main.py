"""Main FastAPI application for the Cursor-Hermes Bridge."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from .api.routes import router
from .services.auth_service import AuthService
from .services.progress_service import ProgressService
from .services.session_service import SessionService
from .services.summary_service import SummaryService
from .services.telegram_service import TelegramService
from .storage.database import Database
from .utils.config import settings
from .utils.logging import get_logger, redact_secrets

logger = get_logger("app.main")


class AppState:
    """Shared application state."""

    def __init__(self) -> None:
        self.database: Database
        self.session_service: SessionService
        self.progress_service: ProgressService
        self.summary_service: SummaryService
        self.auth_service: AuthService
        self.telegram_service: TelegramService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and clean up services."""
    logger.info("Starting Cursor-Hermes Bridge v0.1.0")

    # Initialize storage
    db_path = settings.DATABASE_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    database = Database(db_path)
    await database.initialize()

    # Register configured adapter
    from .adapters.base import adapter_registry
    from .adapters.cursor_logs import CursorLogsAdapter
    logs_adapter = CursorLogsAdapter()
    adapter_registry.register(logs_adapter)
    adapter_registry.set_primary(settings.ADAPTER_PRIMARY)

    # Initialize services
    auth_service = AuthService(database)
    session_service = SessionService(database)
    progress_service = ProgressService(database)
    summary_service = SummaryService(database)
    telegram_service = TelegramService(database, session_service, progress_service, summary_service)

    # Initialize the adapter and sync existing sessions
    await logs_adapter.initialize()
    sync_result = await session_service.sync_with_adapter()
    logger.info("Session sync complete", extra=sync_result)

    # Store in app state
    state = AppState()
    state.database = database
    state.session_service = session_service
    state.progress_service = progress_service
    state.summary_service = summary_service
    state.auth_service = auth_service
    state.telegram_service = telegram_service
    app.state = state

    # Start Telegram bot (only if token is configured)
    if settings.TELEGRAM_BOT_TOKEN:
        await telegram_service.initialize()
        await telegram_service.start_polling()
    else:
        logger.info("Telegram bot disabled — no TELEGRAM_BOT_TOKEN configured")

    logger.info("Cursor-Hermes Bridge started successfully")
    yield

    # Cleanup
    await telegram_service.stop()
    await database.close()
    logger.info("Cursor-Hermes Bridge shut down")


app = FastAPI(
    title="Cursor-Hermes Bridge",
    description="Bridge that lets Hermes monitor and control Cursor from Telegram",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


def run() -> None:
    """Run the application server."""
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
