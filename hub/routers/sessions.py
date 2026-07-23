"""Session CRUD + lifecycle endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import service
from ..models import SessionCreate, SessionUpdate

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
def create(data: SessionCreate):
    return service.create_session(data)


@router.get("")
def list_all():
    return service.list_sessions()


@router.get("/{session_id}")
def detail(session_id: str):
    bundle = service.get_bundle(session_id)
    if bundle is None:
        raise HTTPException(404, "session not found")
    return bundle


@router.patch("/{session_id}")
def update(session_id: str, data: SessionUpdate):
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return service.update_session(session_id, data)


@router.post("/{session_id}/stop")
def stop(session_id: str):
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return service.stop_session(session_id)


@router.delete("/{session_id}")
def delete(session_id: str):
    service.delete_session(session_id)
    return {"ok": True}
