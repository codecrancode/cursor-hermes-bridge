"""Tests for progress service."""
from __future__ import annotations

import pytest

from app.models.progress_event import ProgressEvent
from app.services.progress_service import ProgressService
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_create_progress_event(progress_service: ProgressService, session_service: SessionService):
    session = await session_service.create_session("Test")
    event = await progress_service.create_progress_event(
        session_id=session.id,
        stage="planning",
        detail="Starting work",
    )
    assert event.session_id == session.id
    assert event.stage == "planning"
    assert event.detail == "Starting work"


@pytest.mark.asyncio
async def test_get_progress_events(progress_service: ProgressService, session_service: SessionService):
    session = await session_service.create_session("Test")
    await progress_service.create_progress_event(session.id, "planning", "Planning complete")
    await progress_service.create_progress_event(session.id, "editing", "Editing auth")
    events = await progress_service.get_progress_events(session.id, limit=10)
    assert len(events) == 2


@pytest.mark.asyncio
async def test_get_progress_statistics(progress_service: ProgressService, session_service: SessionService):
    session = await session_service.create_session("Test")
    await progress_service.create_progress_event(session.id, "planning", "Planning complete")
    await progress_service.create_progress_event(session.id, "editing", "Editing auth")
    stats = await progress_service.get_progress_statistics()
    assert isinstance(stats, dict)
    assert stats.get("total_progress_events", 0) == 2
