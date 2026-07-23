"""SQLite storage layer for the session hub.

A single-file database keeps the homelab deployment trivial (just a mounted volume).
Access is synchronous sqlite3; traffic is low (one operator, a handful of collectors),
so a connection-per-call model is more than fast enough and avoids threading pitfalls.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    name          TEXT,
    status        TEXT NOT NULL DEFAULT 'active',   -- active | stopped
    host          TEXT,
    client        TEXT,
    network_path  TEXT,                              -- local-LAN | remote-Tailscale | remote-WAN
    codec         TEXT,                              -- H.264 | HEVC | AV1
    resolution    TEXT,
    fps           INTEGER,
    bitrate_mbps  INTEGER,
    hdr           INTEGER NOT NULL DEFAULT 0,        -- 0/1
    encoder_settings TEXT,                           -- JSON blob of Apollo encoder knobs
    outcome       TEXT NOT NULL DEFAULT 'unknown',   -- unknown | pass | fail | partial
    notes         TEXT DEFAULT '',
    diagnosis     TEXT,                              -- last stored Copilot diagnosis
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    stopped_at    TEXT
);

CREATE TABLE IF NOT EXISTS log_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,       -- host | client
    role        TEXT NOT NULL,       -- apollo | moonlight | artemis
    machine     TEXT,                -- reporting machine name
    content     TEXT NOT NULL DEFAULT '',
    meta        TEXT,                -- JSON
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_chunks_session ON log_chunks(session_id);

CREATE TABLE IF NOT EXISTS link_samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,       -- host | client
    machine     TEXT,
    link_type   TEXT,                -- ethernet | wifi | other
    iface       TEXT,
    ssid        TEXT,
    bssid       TEXT,                -- identifies the physical access point
    band        TEXT,
    channel     TEXT,
    rssi        INTEGER,             -- dBm (wifi)
    signal_pct  INTEGER,             -- % (windows netsh)
    phy_mode    TEXT,                -- 802.11ax, etc.
    link_speed  TEXT,                -- negotiated (e.g. 1 Gbps / 866 Mbps)
    sampled_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_link_samples_session ON link_samples(session_id);

CREATE TABLE IF NOT EXISTS net_tests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool           TEXT NOT NULL DEFAULT 'iperf3',
    direction      TEXT,             -- e.g. server->client (reverse UDP)
    bitrate_target TEXT,
    throughput_mbps REAL,
    jitter_ms      REAL,
    loss_pct       REAL,
    raw            TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_net_tests_session ON net_tests(session_id);

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'overlay_screenshot',
    filename    TEXT NOT NULL,
    caption     TEXT,
    uploaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,       -- user | assistant
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);
"""


def get_conn() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    if "encoder_settings" in d and isinstance(d["encoder_settings"], str):
        try:
            d["encoder_settings"] = json.loads(d["encoder_settings"]) if d["encoder_settings"] else {}
        except json.JSONDecodeError:
            pass
    if "meta" in d and isinstance(d["meta"], str) and d["meta"]:
        try:
            d["meta"] = json.loads(d["meta"])
        except json.JSONDecodeError:
            pass
    return d


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]
