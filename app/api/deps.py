"""FastAPI dependency injection."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from ..services.auth_service import AuthService
from ..services.progress_service import ProgressService
from ..services.session_service import SessionService
from ..services.summary_service import SummaryService
from ..services.telegram_service import TelegramService
from ..utils.config import settings


async def get_state(request: Request):
    """Get application state from request."""
    return request.app.state


async def verify_api_auth(request: Request) -> None:
    """Verify API authentication.

    If API_SECRET_TOKEN is set, all requests must include it in X-API-Key header.
    If token is empty, only localhost requests are allowed.
    """
    token = settings.API_SECRET_TOKEN
    if not token:
        client_host = request.client.host if request.client else "unknown"
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API is bound to localhost only. Set API_SECRET_TOKEN for remote access.",
            )
        return

    api_key = request.headers.get("X-API-Key", "")
    if api_key != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


async def get_session_service(state=Depends(get_state)) -> SessionService:
    return state.session_service


async def get_progress_service(state=Depends(get_state)) -> ProgressService:
    return state.progress_service


async def get_summary_service(state=Depends(get_state)) -> SummaryService:
    return state.summary_service


async def get_telegram_service(state=Depends(get_state)) -> TelegramService:
    return state.telegram_service
