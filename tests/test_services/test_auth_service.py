"""Tests for auth service."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_is_chat_authorized_configured(auth_service: AuthService):
    """A chat ID in the configured list should be authorized."""
    with patch("app.services.auth_service.settings") as mock_settings:
        mock_settings.TELEGRAM_ALLOWED_CHAT_IDS = [12345]
        result = await auth_service.is_chat_authorized(12345)
        assert result is True


@pytest.mark.asyncio
async def test_is_chat_authorized_not_configured(auth_service: AuthService):
    """A chat ID not in the configured list should not be authorized initially."""
    with patch("app.services.auth_service.settings") as mock_settings:
        mock_settings.TELEGRAM_ALLOWED_CHAT_IDS = []
        result = await auth_service.is_chat_authorized(99999)
        assert result is False
