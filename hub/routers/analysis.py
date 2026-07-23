"""Copilot analysis endpoints: run a diagnosis, and chat follow-ups. Opt-in per session."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import copilot, service
from ..models import ChatIn

router = APIRouter(prefix="/api/sessions", tags=["analysis"])


@router.post("/{session_id}/analyze")
def analyze(session_id: str):
    bundle = service.get_bundle(session_id)
    if bundle is None:
        raise HTTPException(404, "session not found")
    related = service.get_related_sessions(session_id)
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
    related = service.get_related_sessions(session_id)
    reply = copilot.chat(bundle, history, msg.message, related)
    service.add_chat(session_id, "assistant", reply)
    return {"reply": reply}
