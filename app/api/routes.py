"""API routes for the Cursor-Hermes Bridge."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.session_service import SessionService
from app.services.summary_service import SummaryService
from app.api.deps import get_session_service, get_summary_service, verify_api_auth

router = APIRouter(dependencies=[Depends(verify_api_auth)])


@router.get("/status")
async def get_status(
    session_service: SessionService = Depends(get_session_service),
):
    """Get current Cursor status."""
    active = await session_service.get_active_session()
    if active:
        return {"status": "active", "session": active.to_dict()}
    return {"status": "idle", "session": None}


@router.post("/sessions")
async def create_session(
    name: str = "New Cursor Session",
    session_service: SessionService = Depends(get_session_service),
):
    """Create a new Cursor session."""
    try:
        session = await session_service.create_session(name)
        return session.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    session_service: SessionService = Depends(get_session_service),
):
    """List recent Cursor sessions."""
    sessions = await session_service.list_sessions(limit)
    return {"sessions": [s.to_dict() for s in sessions], "count": len(sessions)}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """Get details for a specific session."""
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session.to_dict()


@router.post("/sessions/{session_id}/activate")
async def activate_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """Set a session as the active session."""
    result = await session_service.set_active_session(session_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"status": "activated", "session_id": session_id}


@router.post("/sessions/{session_id}/pause")
async def pause_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """Pause a session."""
    result = await session_service.pause_session(session_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"status": "paused", "session_id": session_id}


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """Resume a paused session."""
    result = await session_service.resume_session(session_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"status": "resumed", "session_id": session_id}


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """Mark a session as completed."""
    result = await session_service.complete_session(session_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"status": "completed", "session_id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """Delete a session."""
    result = await session_service.delete_session(session_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
    summary_service: SummaryService = Depends(get_summary_service),
):
    """Get a summary of a session's progress."""
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    summary = await summary_service.summarize_session(session_id)
    return {"session_id": session_id, "summary": summary}


@router.get("/stats")
async def get_stats(
    session_service: SessionService = Depends(get_session_service),
):
    """Get session statistics."""
    stats = await session_service.get_session_statistics()
    return stats
