"""Ingestion endpoints the collectors push to: logs, displays, link samples, net tests, artifacts."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import config, service
from ..models import DisplaySampleBatch, LinkSampleBatch, LogChunkIn, NetTestIn

router = APIRouter(prefix="/api/sessions", tags=["ingest"])


def _require(session_id: str) -> None:
    if service.get_session(session_id) is None:
        raise HTTPException(404, "session not found")


@router.post("/{session_id}/logs")
def add_log(session_id: str, chunk: LogChunkIn):
    _require(session_id)
    return {"id": service.add_log_chunk(session_id, chunk)}


@router.post("/{session_id}/links")
def add_links(session_id: str, batch: LinkSampleBatch):
    _require(session_id)
    return {"added": service.add_link_samples(session_id, batch.samples)}


@router.post("/{session_id}/displays")
def add_displays(session_id: str, batch: DisplaySampleBatch):
    _require(session_id)
    return {"added": service.add_display_samples(session_id, batch.samples)}


@router.post("/{session_id}/nettests")
def add_nettest(session_id: str, test: NetTestIn):
    _require(session_id)
    return {"id": service.add_net_test(session_id, test)}


@router.post("/{session_id}/artifacts")
async def add_artifact(
    session_id: str,
    file: UploadFile = File(...),
    kind: str = Form("overlay_screenshot"),
    caption: str | None = Form(None),
):
    _require(session_id)
    config.ensure_dirs()
    safe = f"{session_id}_{service.new_session_id()}_{(file.filename or 'upload').replace('/', '_')}"
    dest = config.ARTIFACTS_DIR / safe
    dest.write_bytes(await file.read())
    aid = service.add_artifact(session_id, kind, safe, caption)
    return {"id": aid, "filename": safe}
