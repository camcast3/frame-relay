"""Copilot analysis endpoints: run a diagnosis, and chat follow-ups. Opt-in per session."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import copilot, service
from ..models import ChatIn

router = APIRouter(prefix="/api/sessions", tags=["analysis"])


def _comparison_peers(bundle):
    session = bundle["session"]
    label = session.get("comparison_label")
    if label:
        candidates = [
            s for s in service.get_comparison_sessions(label) if s["id"] != session["id"]
        ]
        return [
            peer for peer in candidates
            if service.comparison_compatibility([session, peer])["compatible"]
        ]
    return service.get_related_sessions(session["id"])


@router.post("/{session_id}/analyze")
def analyze(session_id: str):
    bundle = service.get_bundle(session_id)
    if bundle is None:
        raise HTTPException(404, "session not found")
    related = _comparison_peers(bundle)
    diagnosis = copilot.diagnose(bundle, related)
    service.set_diagnosis(session_id, diagnosis)
    return {"diagnosis": diagnosis}


@router.get("/{session_id}/chat")
def chat_history(session_id: str):
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return service.get_chat(session_id)


@router.post("/{session_id}/chat")
def chat(session_id: str, msg: ChatIn):
    bundle = service.get_bundle(session_id)
    if bundle is None:
        raise HTTPException(404, "session not found")
    service.add_chat(session_id, "user", msg.message)
    history = service.get_chat(session_id)
    related = _comparison_peers(bundle)
    reply = copilot.chat(bundle, history, msg.message, related)
    service.add_chat(session_id, "assistant", reply)
    return {"reply": reply}
