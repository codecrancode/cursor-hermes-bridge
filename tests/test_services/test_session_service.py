"""Tests for session service."""
from __future__ import annotations

import pytest

from app.models.session import Session, SessionStatus
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_create_session(session_service: SessionService):
    session = await session_service.create_session("Test Session")
    assert session.name == "Test Session"
    assert session.status == SessionStatus.IDLE
    assert session.id is not None


@pytest.mark.asyncio
async def test_get_session(session_service: SessionService):
    created = await session_service.create_session("Test Session")
    fetched = await session_service.get_session(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Test Session"


@pytest.mark.asyncio
async def test_get_nonexistent_session(session_service: SessionService):
    session = await session_service.get_session("nonexistent")
    assert session is None


@pytest.mark.asyncio
async def test_list_sessions(session_service: SessionService):
    await session_service.create_session("Session 1")
    await session_service.create_session("Session 2")
    sessions = await session_service.list_sessions()
    assert len(sessions) >= 2


@pytest.mark.asyncio
async def test_update_session_status(session_service: SessionService):
    session = await session_service.create_session("Test")
    result = await session_service.update_session_status(session.id, SessionStatus.ACTIVE)
    assert result is True
    updated = await session_service.get_session(session.id)
    assert updated is not None
    assert updated.status == SessionStatus.ACTIVE
