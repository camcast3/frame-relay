"""Data-access/service layer shared by the API routers, HTML views, and Copilot analyzer."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from . import db
from .models import (
    DisplaySampleIn,
    LinkSampleIn,
    LogChunkIn,
    NetTestIn,
    SessionCreate,
    SessionObservationPatch,
    SessionUpdate,
    Source,
)

SESSION_JSON_FIELDS = frozenset(db.SESSION_JSON_COLUMNS)
OBSERVATION_SCALAR_FIELDS = (
    "comparison_label",
    "apollo_app",
    "game_title",
    "client_role",
    "client_platform",
    "client_version",
)
COMPARISON_REQUESTED_FIELDS = ("codec", "resolution", "fps", "bitrate_mbps", "hdr")
SCREENSHOT_REQUEST_SELECT = """
SELECT sr.*,
       a.filename AS artifact_filename,
       a.kind AS artifact_kind,
       a.caption AS artifact_caption
FROM screenshot_requests sr
LEFT JOIN artifacts a ON a.id = sr.artifact_id
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def _explicit_model_fields(model: BaseModel) -> dict[str, Any]:
    return {name: getattr(model, name) for name in model.model_fields_set}


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {name: _json_value(getattr(value, name)) for name in value.model_fields_set}
    if isinstance(value, dict):
        return {name: _json_value(item) for name, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _json_column_payload(value: Any) -> Any:
    if value is None:
        return {}
    return _json_value(value)


def _serialize_session_value(key: str, value: Any) -> Any:
    if key in SESSION_JSON_FIELDS:
        return json.dumps(_json_column_payload(value))
    if key == "hdr":
        return 1 if value else 0
    return value


def _apply_session_updates(session_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    sets, values = [], []
    for key, value in fields.items():
        sets.append(f"{key}=?")
        values.append(_serialize_session_value(key, value))
    values.append(session_id)
    with db.db() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", values)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (dict, list)):
        return bool(value)
    return True


def _merge_missing(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, incoming_value in incoming.items():
        if not _has_value(incoming_value):
            continue
        if isinstance(incoming_value, dict):
            existing_value = merged.get(key)
            if isinstance(existing_value, dict):
                merged[key] = _merge_missing(existing_value, incoming_value)
            elif key not in merged or _is_blank(existing_value):
                merged[key] = _merge_missing({}, incoming_value)
            continue
        if key not in merged or _is_blank(merged.get(key)):
            merged[key] = incoming_value
    return merged


def _collect_distinct(values: list[Any]) -> list[Any]:
    distinct: list[Any] = []
    for value in values:
        if not _has_value(value):
            continue
        if isinstance(value, str):
            value = value.strip()
        if value not in distinct:
            distinct.append(value)
    return distinct


class ScreenshotRequestNotFoundError(LookupError):
    pass


class ScreenshotRequestConflictError(RuntimeError):
    pass


def _insert_artifact(
    conn: Any,
    session_id: str,
    kind: str,
    filename: str,
    caption: str | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO artifacts (session_id, kind, filename, caption, uploaded_at) VALUES (?,?,?,?,?)",
        (session_id, kind, filename, caption, _now()),
    )
    return int(cur.lastrowid)


def _fetch_screenshot_requests(
    conn: Any,
    where: str,
    args: list[Any],
) -> list[dict[str, Any]]:
    query = SCREENSHOT_REQUEST_SELECT
    if where:
        query += f" WHERE {where}"
    query += " ORDER BY sr.id ASC"
    return db.rows_to_dicts(conn.execute(query, args).fetchall())


def _fetch_screenshot_request(
    conn: Any,
    session_id: str,
    request_id: int,
) -> dict[str, Any] | None:
    rows = _fetch_screenshot_requests(conn, "sr.session_id=? AND sr.id=?", [session_id, request_id])
    return rows[0] if rows else None


def _require_pending_screenshot_request(
    conn: Any,
    session_id: str,
    request_id: int,
    source: Source,
) -> None:
    if conn.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone() is None:
        raise ScreenshotRequestNotFoundError("session not found")

    row = conn.execute(
        "SELECT target_source, status FROM screenshot_requests WHERE id=? AND session_id=?",
        (request_id, session_id),
    ).fetchone()
    if row is None:
        raise ScreenshotRequestNotFoundError("screenshot request not found")
    if row["target_source"] != source:
        raise ScreenshotRequestConflictError("screenshot request target does not match source")
    if row["status"] != "pending":
        raise ScreenshotRequestConflictError("screenshot request is not pending")


# --- sessions -------------------------------------------------------------------

def create_session(data: SessionCreate) -> dict[str, Any]:
    sid = new_session_id()
    now = _now()
    with db.db() as conn:
        conn.execute(
            """INSERT INTO sessions
               (id, name, status, host, client, comparison_label, apollo_app, game_title,
                client_role, client_platform, client_version, network_path, codec,
                resolution, fps, bitrate_mbps, hdr, encoder_settings, requested_settings,
                hdr_details, visual_assessment, outcome, notes, created_at, started_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid, data.name, "active", data.host, data.client, data.comparison_label,
                data.apollo_app, data.game_title, data.client_role, data.client_platform,
                data.client_version, data.network_path, data.codec, data.resolution,
                data.fps, data.bitrate_mbps, 1 if data.hdr else 0,
                json.dumps(_json_column_payload(data.encoder_settings)),
                json.dumps(_json_column_payload(data.requested_settings)),
                json.dumps(_json_column_payload(data.hdr_details)),
                json.dumps(_json_column_payload(data.visual_assessment)),
                "unknown", data.notes or "", now, now,
            ),
        )
    return get_session(sid)  # type: ignore[return-value]


def list_sessions(awaiting_client: bool = False,
                  awaiting_host: bool = False) -> list[dict[str, Any]]:
    """List sessions, newest first.

    "Awaiting a client/host" means that side has not posted any log yet - not merely that the
    corresponding metadata field is blank. The host collector fills the client name in from the
    live connection while it is still running, so keying off names would hide a session from the
    other collector seconds after the first one starts. A stopped session awaits nobody.
    """
    q = "SELECT * FROM sessions"
    clauses: list[str] = []
    if awaiting_client or awaiting_host:
        clauses.append("status != 'stopped'")
    for flag, source in ((awaiting_client, "client"), (awaiting_host, "host")):
        if flag:
            clauses.append(
                "NOT EXISTS (SELECT 1 FROM log_chunks lc"
                f" WHERE lc.session_id = sessions.id AND lc.source = '{source}')"
            )
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY created_at DESC"
    with db.db() as conn:
        rows = conn.execute(q).fetchall()
    return db.rows_to_dicts(rows)


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    with db.db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return db.row_to_dict(row)


def update_session(session_id: str, data: SessionUpdate) -> Optional[dict[str, Any]]:
    fields = _explicit_model_fields(data)
    if not fields:
        return get_session(session_id)
    _apply_session_updates(session_id, fields)
    return get_session(session_id)


def merge_session_observations(
    session_id: str,
    patch: SessionObservationPatch,
) -> Optional[dict[str, Any]]:
    session = get_session(session_id)
    if session is None:
        return None

    updates: dict[str, Any] = {}
    for field in OBSERVATION_SCALAR_FIELDS:
        incoming = getattr(patch, field)
        if _has_value(incoming) and _is_blank(session.get(field)):
            updates[field] = incoming

    for field in ("requested_settings", "hdr_details"):
        incoming = _json_column_payload(getattr(patch, field))
        if not incoming:
            continue
        existing = session.get(field)
        existing_dict = existing if isinstance(existing, dict) else {}
        merged = _merge_missing(existing_dict, incoming)
        if merged != existing_dict:
            updates[field] = merged

    if not updates:
        return session
    _apply_session_updates(session_id, updates)
    return get_session(session_id)


def stop_session(session_id: str) -> Optional[dict[str, Any]]:
    with db.db() as conn:
        conn.execute(
            "UPDATE sessions SET status='stopped', stopped_at=? WHERE id=?",
            (_now(), session_id),
        )
    return get_session(session_id)


def delete_session(session_id: str) -> None:
    with db.db() as conn:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def set_diagnosis(session_id: str, text: str) -> None:
    with db.db() as conn:
        conn.execute("UPDATE sessions SET diagnosis=? WHERE id=?", (text, session_id))


# --- children -------------------------------------------------------------------

def add_log_chunk(session_id: str, chunk: LogChunkIn) -> int:
    with db.db() as conn:
        cur = conn.execute(
            """INSERT INTO log_chunks (session_id, source, role, machine, content, meta, captured_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, chunk.source, chunk.role, chunk.machine, chunk.content,
             json.dumps(chunk.meta or {}), _now()),
        )
        return int(cur.lastrowid)


def get_log_chunks(session_id: str, source: Optional[str] = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM log_chunks WHERE session_id=?"
    args: list[Any] = [session_id]
    if source:
        q += " AND source=?"
        args.append(source)
    q += " ORDER BY id ASC"
    with db.db() as conn:
        return db.rows_to_dicts(conn.execute(q, args).fetchall())


def add_link_samples(session_id: str, samples: list[LinkSampleIn]) -> int:
    now = _now()
    n = 0
    with db.db() as conn:
        for s in samples:
            conn.execute(
                """INSERT INTO link_samples
                   (session_id, source, machine, link_type, iface, ssid, bssid, band,
                    channel, rssi, signal_pct, phy_mode, link_speed, sampled_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, s.source, s.machine, s.link_type, s.iface, s.ssid, s.bssid,
                 s.band, s.channel, s.rssi, s.signal_pct, s.phy_mode, s.link_speed,
                 s.sampled_at or now),
            )
            n += 1
    return n


def get_link_samples(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM link_samples WHERE session_id=? ORDER BY sampled_at ASC, id ASC",
            (session_id,),
        ).fetchall()
    return db.rows_to_dicts(rows)


def add_display_samples(session_id: str, samples: list[DisplaySampleIn]) -> int:
    now = _now()
    n = 0
    with db.db() as conn:
        for sample in samples:
            conn.execute(
                """INSERT INTO display_samples
                   (session_id, source, machine, phase, adapter_id, adapter_device_path,
                    source_id, target_id, source_name, friendly_name, device_path,
                    is_virtual, "primary", width, height, refresh_hz, rotation,
                    scaling, output_technology, hdr_supported, hdr_enabled,
                    bits_per_channel, color_encoding, sampled_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    sample.source,
                    sample.machine,
                    sample.phase,
                    sample.adapter_id,
                    sample.adapter_device_path,
                    sample.source_id,
                    sample.target_id,
                    sample.source_name,
                    sample.friendly_name,
                    sample.device_path,
                    sample.is_virtual,
                    sample.primary,
                    sample.width,
                    sample.height,
                    sample.refresh_hz,
                    sample.rotation,
                    sample.scaling,
                    sample.output_technology,
                    sample.hdr_supported,
                    sample.hdr_enabled,
                    sample.bits_per_channel,
                    sample.color_encoding,
                    sample.sampled_at or now,
                ),
            )
            n += 1
    return n


def get_display_samples(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM display_samples WHERE session_id=? ORDER BY sampled_at ASC, id ASC",
            (session_id,),
        ).fetchall()
    return db.rows_to_dicts(rows)


def add_net_test(session_id: str, test: NetTestIn) -> int:
    with db.db() as conn:
        cur = conn.execute(
            """INSERT INTO net_tests
               (session_id, tool, direction, bitrate_target, throughput_mbps, jitter_ms,
                loss_pct, raw, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (session_id, test.tool, test.direction, test.bitrate_target,
             test.throughput_mbps, test.jitter_ms, test.loss_pct, test.raw, _now()),
        )
        return int(cur.lastrowid)


def get_net_tests(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM net_tests WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
    return db.rows_to_dicts(rows)


def add_artifact(session_id: str, kind: str, filename: str, caption: str | None) -> int:
    with db.db() as conn:
        return _insert_artifact(conn, session_id, kind, filename, caption)


def get_artifacts(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
    return db.rows_to_dicts(rows)


def create_screenshot_requests(session_id: str, targets: list[Source]) -> list[dict[str, Any]]:
    requested_at = _now()
    request_ids: list[int] = []
    with db.db() as conn:
        for target in targets:
            cur = conn.execute(
                """INSERT INTO screenshot_requests
                   (session_id, target_source, requested_at)
                   VALUES (?,?,?)""",
                (session_id, target, requested_at),
            )
            request_ids.append(int(cur.lastrowid))

        if not request_ids:
            return []

        placeholders = ",".join("?" for _ in request_ids)
        return _fetch_screenshot_requests(conn, f"sr.id IN ({placeholders})", request_ids)


def get_screenshot_requests(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        return _fetch_screenshot_requests(conn, "sr.session_id=?", [session_id])


def get_pending_screenshot_requests(session_id: str, source: Source) -> list[dict[str, Any]]:
    with db.db() as conn:
        return _fetch_screenshot_requests(
            conn,
            "sr.session_id=? AND sr.status='pending' AND sr.target_source=?",
            [session_id, source],
        )


def complete_screenshot_request(
    session_id: str,
    request_id: int,
    source: Source,
    filename: str,
    machine: str | None,
    caption: str,
    kind: str,
    completed_at: str | None = None,
) -> dict[str, Any]:
    finished_at = completed_at or _now()
    with db.db() as conn:
        cur = conn.execute(
            """UPDATE screenshot_requests
               SET status='completed', completed_at=?, machine=?, artifact_id=NULL, error=NULL
               WHERE id=? AND session_id=? AND target_source=? AND status='pending'""",
            (finished_at, machine, request_id, session_id, source),
        )
        if cur.rowcount != 1:
            _require_pending_screenshot_request(conn, session_id, request_id, source)
            raise ScreenshotRequestConflictError("screenshot request is not pending")
        artifact_id = _insert_artifact(conn, session_id, kind, filename, caption)
        conn.execute(
            "UPDATE screenshot_requests SET artifact_id=? WHERE id=?",
            (artifact_id, request_id),
        )
        row = _fetch_screenshot_request(conn, session_id, request_id)
    if row is None:
        raise ScreenshotRequestNotFoundError("screenshot request not found")
    return row


def fail_screenshot_request(
    session_id: str,
    request_id: int,
    source: Source,
    error: str,
    machine: str | None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    finished_at = completed_at or _now()
    with db.db() as conn:
        cur = conn.execute(
            """UPDATE screenshot_requests
               SET status='failed', completed_at=?, machine=?, artifact_id=NULL, error=?
               WHERE id=? AND session_id=? AND target_source=? AND status='pending'""",
            (finished_at, machine, error, request_id, session_id, source),
        )
        if cur.rowcount != 1:
            _require_pending_screenshot_request(conn, session_id, request_id, source)
            raise ScreenshotRequestConflictError("screenshot request is not pending")
        row = _fetch_screenshot_request(conn, session_id, request_id)
    if row is None:
        raise ScreenshotRequestNotFoundError("screenshot request not found")
    return row


def add_chat(session_id: str, role: str, content: str) -> int:
    with db.db() as conn:
        cur = conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
            (session_id, role, content, _now()),
        )
        return int(cur.lastrowid)


def get_chat(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
    return db.rows_to_dicts(rows)


# --- aggregates -----------------------------------------------------------------

def get_bundle(session_id: str) -> Optional[dict[str, Any]]:
    """Everything about one session, used by the detail view and the analyzer."""
    session = get_session(session_id)
    if session is None:
        return None
    return {
        "session": session,
        "host_logs": get_log_chunks(session_id, "host"),
        "client_logs": get_log_chunks(session_id, "client"),
        "link_samples": get_link_samples(session_id),
        "display_samples": get_display_samples(session_id),
        "net_tests": get_net_tests(session_id),
        "artifacts": get_artifacts(session_id),
        "screenshot_requests": get_screenshot_requests(session_id),
        "chat": get_chat(session_id),
    }


def get_related_sessions(session_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Other sessions with the same host/client (any network path) for comparison."""
    s = get_session(session_id)
    if not s:
        return []
    with db.db() as conn:
        rows = conn.execute(
            """SELECT * FROM sessions
               WHERE id != ? AND (host IS ? OR client IS ?)
               ORDER BY created_at DESC LIMIT ?""",
            (session_id, s.get("host"), s.get("client"), limit),
        ).fetchall()
    return db.rows_to_dicts(rows)


def get_comparison_sessions(comparison_label: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE comparison_label=? ORDER BY created_at ASC",
            (comparison_label,),
        ).fetchall()
    return db.rows_to_dicts(rows)


def comparison_compatibility(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    mismatches: dict[str, Any] = {}
    for field in ("host", "apollo_app", "game_title", "network_path"):
        values = _collect_distinct([session.get(field) for session in sessions])
        if len(values) > 1:
            mismatches[field] = values

    requested_mismatches: dict[str, list[Any]] = {}
    for field in COMPARISON_REQUESTED_FIELDS:
        values = _collect_distinct([
            (session.get("requested_settings") or {}).get(field)
            if isinstance(session.get("requested_settings"), dict)
            else None
            for session in sessions
        ])
        if len(values) > 1:
            requested_mismatches[field] = values

    if requested_mismatches:
        mismatches["requested_settings"] = requested_mismatches

    return {"compatible": not mismatches, "mismatches": mismatches}
