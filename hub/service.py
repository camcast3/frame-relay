"""Data-access/service layer shared by the API routers, HTML views, and Copilot analyzer."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from . import db
from .models import (
    LinkSampleIn,
    LogChunkIn,
    NetTestIn,
    SessionCreate,
    SessionUpdate,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


# --- sessions -------------------------------------------------------------------

def create_session(data: SessionCreate) -> dict[str, Any]:
    sid = new_session_id()
    now = _now()
    with db.db() as conn:
        conn.execute(
            """INSERT INTO sessions
               (id, name, status, host, client, network_path, codec, resolution, fps,
                bitrate_mbps, hdr, encoder_settings, outcome, notes, created_at, started_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid, data.name, "active", data.host, data.client, data.network_path,
                data.codec, data.resolution, data.fps, data.bitrate_mbps,
                1 if data.hdr else 0, json.dumps(data.encoder_settings or {}),
                "unknown", data.notes or "", now, now,
            ),
        )
    return get_session(sid)  # type: ignore[return-value]


def list_sessions(awaiting_client: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM sessions"
    if awaiting_client:
        # "Awaiting a client" means no client has actually attached yet - i.e. no client log
        # chunks - rather than merely that the client *name* field is blank. The host collector
        # fills that name in from the live connection while it is still running, so keying off
        # it would hide the session from the client collector seconds after the host starts.
        q += (" WHERE status != 'stopped'"
              " AND NOT EXISTS (SELECT 1 FROM log_chunks lc"
              " WHERE lc.session_id = sessions.id AND lc.source = 'client')")
    q += " ORDER BY created_at DESC"
    with db.db() as conn:
        rows = conn.execute(q).fetchall()
    return db.rows_to_dicts(rows)


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    with db.db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return db.row_to_dict(row)


def update_session(session_id: str, data: SessionUpdate) -> Optional[dict[str, Any]]:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        return get_session(session_id)
    sets, values = [], []
    for key, val in fields.items():
        if key == "encoder_settings":
            val = json.dumps(val or {})
        elif key == "hdr":
            val = 1 if val else 0
        sets.append(f"{key}=?")
        values.append(val)
    values.append(session_id)
    with db.db() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", values)
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
        cur = conn.execute(
            "INSERT INTO artifacts (session_id, kind, filename, caption, uploaded_at) VALUES (?,?,?,?,?)",
            (session_id, kind, filename, caption, _now()),
        )
        return int(cur.lastrowid)


def get_artifacts(session_id: str) -> list[dict[str, Any]]:
    with db.db() as conn:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
    return db.rows_to_dicts(rows)


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
        "net_tests": get_net_tests(session_id),
        "artifacts": get_artifacts(session_id),
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
