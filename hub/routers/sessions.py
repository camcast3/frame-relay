"""Session CRUD + lifecycle endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import display_validation, service
from ..models import SessionCreate, SessionObservationPatch, SessionUpdate

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
def create(data: SessionCreate):
    return service.create_session(data)


@router.get("")
def list_all(awaiting_client: bool = False, awaiting_host: bool = False):
    """List sessions, newest first.

    `?awaiting_client=true` returns active sessions no client has posted a log to yet (the
    host-first workflow); `?awaiting_host=true` is the mirror image, used by a host collector
    running in watch mode to pick up a session the client just created.
    """
    return service.list_sessions(awaiting_client=awaiting_client, awaiting_host=awaiting_host)


@router.get("/comparisons/{comparison_label}")
def comparison_detail(comparison_label: str):
    sessions = service.get_comparison_sessions(comparison_label)
    if not sessions:
        raise HTTPException(404, "comparison not found")
    return {
        "label": comparison_label,
        "sessions": sessions,
        "compatibility": service.comparison_compatibility(sessions),
    }


@router.get("/{session_id}")
def detail(session_id: str):
    bundle = service.get_bundle(session_id)
    if bundle is None:
        raise HTTPException(404, "session not found")
    bundle["display_validation"] = display_validation.summarize(
        bundle["session"], bundle.get("display_samples", [])
    )
    return bundle


@router.patch("/{session_id}")
def update(session_id: str, data: SessionUpdate):
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return service.update_session(session_id, data)


@router.post("/{session_id}/observations")
def merge_observations(session_id: str, data: SessionObservationPatch):
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return service.merge_session_observations(session_id, data)


@router.post("/{session_id}/stop")
def stop(session_id: str):
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return service.stop_session(session_id)


@router.delete("/{session_id}")
def delete(session_id: str):
    service.delete_session(session_id)
    return {"ok": True}
