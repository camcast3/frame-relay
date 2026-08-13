"""Authenticated screenshot-request endpoints for host/client capture helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from .. import config, service
from ..models import ScreenshotRequestFailIn, ScreenshotRequestIn, Source

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _require_screenshot_auth(token: str | None) -> None:
    if not config.SCREENSHOT_TOKEN:
        raise HTTPException(503, "screenshot requests are disabled")
    if token is None or not secrets.compare_digest(token, config.SCREENSHOT_TOKEN):
        raise HTTPException(401, "invalid screenshot token")


def _require_session(session_id: str) -> dict[str, object]:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    return session


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _screenshot_filename(session_id: str, request_id: int, source: Source) -> str:
    return f"{session_id}_request_{request_id}_{source}_{service.new_session_id()}.png"


def _caption(source: Source, display_name: str | None, captured_at: str) -> str:
    parts = [f"Requested {source} screenshot"]
    if display_name:
        parts.append(f"display {display_name}")
    parts.append(f"captured at {captured_at}")
    return " — ".join(parts)


def _require_png(content: bytes) -> None:
    if not content.startswith(PNG_SIGNATURE):
        raise HTTPException(400, "file must be a PNG")


async def _read_png_upload(file: UploadFile) -> bytes:
    max_upload_bytes = config.SCREENSHOT_MAX_UPLOAD_BYTES
    content = await file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(413, "file too large")
    _require_png(content)
    return content


def _as_not_found_or_conflict(exc: Exception) -> HTTPException:
    if isinstance(exc, service.ScreenshotRequestNotFoundError):
        return HTTPException(404, str(exc))
    return HTTPException(409, str(exc))


def _auth_dependency(
    x_asl_screenshot_token: str | None = Header(default=None, alias="X-ASL-Screenshot-Token"),
) -> None:
    _require_screenshot_auth(x_asl_screenshot_token)


def _cleanup_file_best_effort(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


router = APIRouter(
    prefix="/api/sessions/{session_id}/screenshot-requests",
    tags=["screenshot-requests"],
    dependencies=[Depends(_auth_dependency)],
)


@router.post("")
def queue_screenshot_requests(session_id: str, data: ScreenshotRequestIn):
    session = _require_session(session_id)
    if session.get("status") == "stopped":
        raise HTTPException(409, "session is stopped")
    return service.create_screenshot_requests(session_id, data.targets)


@router.get("/pending")
def pending_screenshot_requests(session_id: str, source: Source):
    _require_session(session_id)
    return service.get_pending_screenshot_requests(session_id, source)


@router.post("/{request_id}/complete")
async def complete_screenshot_request(
    session_id: str,
    request_id: int,
    file: UploadFile = File(...),
    source: Source = Form(...),
    machine: str | None = Form(None),
    captured_at: str | None = Form(None),
    display_name: str | None = Form(None),
):
    _require_session(session_id)
    content = await _read_png_upload(file)

    captured_time = _normalize_optional_text(captured_at) or datetime.now(timezone.utc).isoformat()
    machine_name = _normalize_optional_text(machine)
    display = _normalize_optional_text(display_name)
    filename = _screenshot_filename(session_id, request_id, source)
    destination = config.ARTIFACTS_DIR / filename
    config.ensure_dirs()
    destination.write_bytes(content)

    try:
        return service.complete_screenshot_request(
            session_id=session_id,
            request_id=request_id,
            source=source,
            filename=filename,
            machine=machine_name,
            caption=_caption(source, display, captured_time),
            kind=f"requested_{source}_screenshot",
            completed_at=captured_time,
        )
    except (service.ScreenshotRequestConflictError, service.ScreenshotRequestNotFoundError) as exc:
        _cleanup_file_best_effort(destination)
        raise _as_not_found_or_conflict(exc) from exc


@router.post("/{request_id}/fail")
def fail_screenshot_request(session_id: str, request_id: int, data: ScreenshotRequestFailIn):
    _require_session(session_id)
    try:
        return service.fail_screenshot_request(
            session_id=session_id,
            request_id=request_id,
            source=data.source,
            error=data.error,
            machine=_normalize_optional_text(data.machine),
        )
    except (service.ScreenshotRequestConflictError, service.ScreenshotRequestNotFoundError) as exc:
        raise _as_not_found_or_conflict(exc) from exc
