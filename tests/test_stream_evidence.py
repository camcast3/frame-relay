from __future__ import annotations

import sqlite3

from asl_collector import clientmeta, hostmeta
from hub import config, db as hub_db
from conftest import SAMPLES


def _create(client, **kw):
    payload = {"name": "comparison", "host": "DOMINO", "client": "couch"}
    payload.update(kw)
    r = client.post("/api/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_stream_evidence_round_trip_and_replace(client):
    session = _create(
        client,
        comparison_label="set-a",
        apollo_app="Apollo",
        game_title="Control",
        client_role="moonlight",
        client_platform="Windows",
        client_version="1.0.0",
        requested_settings={"codec": "HEVC", "resolution": "3840x2160", "hdr": True},
        hdr_details={"requested": True, "encoded_hdr": True, "bit_depth": 10},
        visual_assessment={"rating": 4, "brightness": "good", "artifact_ids": [7, 9]},
    )
    sid = session["id"]
    assert session["requested_settings"] == {
        "codec": "HEVC",
        "resolution": "3840x2160",
        "hdr": True,
    }
    assert session["hdr_details"] == {"requested": True, "encoded_hdr": True, "bit_depth": 10}
    assert session["visual_assessment"] == {
        "rating": 4,
        "brightness": "good",
        "artifact_ids": [7, 9],
    }

    r = client.patch(
        f"/api/sessions/{sid}",
        json={
            "requested_settings": {"codec": "AV1"},
            "hdr_details": {
                "status": "confirmed",
                "evidence": ["operator"],
                "confidence": 1.0,
            },
            "visual_assessment": {"rating": 5, "notes": "excellent"},
        },
    )
    assert r.status_code == 200, r.text

    got = client.get(f"/api/sessions/{sid}").json()["session"]
    assert got["comparison_label"] == "set-a"
    assert got["apollo_app"] == "Apollo"
    assert got["game_title"] == "Control"
    assert got["client_role"] == "moonlight"
    assert got["client_platform"] == "Windows"
    assert got["client_version"] == "1.0.0"
    assert got["requested_settings"] == {"codec": "AV1"}
    assert got["hdr_details"] == {
        "status": "confirmed",
        "evidence": ["operator"],
        "confidence": 1.0,
    }
    assert got["visual_assessment"] == {"rating": 5, "notes": "excellent"}


def test_observation_merge_only_fills_missing_values(client):
    session = _create(
        client,
        game_title="Manual Title",
        requested_settings={"codec": "HEVC", "fps": 60},
        hdr_details={"requested": True},
    )
    sid = session["id"]

    r = client.post(
        f"/api/sessions/{sid}/observations",
        json={
            "comparison_label": "set-b",
            "apollo_app": "Sunshine",
            "game_title": "Observed Title",
            "client_role": "artemis",
            "client_platform": "Android",
            "client_version": "12.3",
            "requested_settings": {
                "codec": "AV1",
                "resolution": "2560x1440",
                "fps": 120,
                "hdr": False,
            },
            "hdr_details": {
                "requested": False,
                "encoded_hdr": True,
                "color_primaries": "BT.2020",
                "evidence": ["overlay"],
            },
        },
    )
    assert r.status_code == 200, r.text
    got = r.json()

    assert got["comparison_label"] == "set-b"
    assert got["apollo_app"] == "Sunshine"
    assert got["game_title"] == "Manual Title"
    assert got["client_role"] == "artemis"
    assert got["client_platform"] == "Android"
    assert got["client_version"] == "12.3"
    assert got["requested_settings"] == {
        "codec": "HEVC",
        "fps": 60,
        "resolution": "2560x1440",
        "hdr": False,
    }
    assert got["hdr_details"] == {
        "requested": True,
        "encoded_hdr": True,
        "color_primaries": "BT.2020",
        "evidence": ["overlay"],
    }


def test_collector_parser_hdr_shapes_survive_api_validation(client):
    session = _create(client)
    sid = session["id"]
    client_parsed = clientmeta.parse_client_metadata(
        (SAMPLES / "moonlight-metadata.log").read_text(), "moonlight"
    )
    r = client.post(
        f"/api/sessions/{sid}/observations",
        json={
            "client_role": "moonlight",
            "client_version": client_parsed["client_version"],
            "requested_settings": client_parsed["requested_settings"],
            "hdr_details": client_parsed["hdr_details"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["hdr_details"]["client_decoder"] == "FFmpeg-based"
    assert r.json()["hdr_details"]["client_display_hdr"] is True
    assert r.json()["hdr_details"]["transfer_function"] == "SMPTE 2084 PQ"

    host_session = _create(client)
    host_parsed = hostmeta.parse_apollo_metadata(
        (SAMPLES / "apollo-metadata-rich.log").read_text()
    )
    r = client.post(
        f"/api/sessions/{host_session['id']}/observations",
        json={
            "requested_settings": host_parsed["requested_settings"],
            "hdr_details": host_parsed["hdr_details"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["hdr_details"]["host_display_hdr"] is True
    assert r.json()["hdr_details"]["encoded_hdr"] is True


def test_comparison_endpoint_reports_compatibility(client):
    first = _create(
        client,
        comparison_label="set-c",
        apollo_app="Apollo",
        game_title="Alan Wake 2",
        network_path="remote-Tailscale",
        requested_settings={"codec": "HEVC", "resolution": "2560x1440", "fps": 60},
    )
    second = _create(
        client,
        comparison_label="set-c",
        apollo_app="Apollo",
        game_title="Alan Wake 2",
        network_path="remote-Tailscale",
        requested_settings={"codec": "AV1", "resolution": "2560x1440", "fps": 60},
    )

    r = client.get("/api/sessions/comparisons/set-c")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["label"] == "set-c"
    assert [item["id"] for item in body["sessions"]] == [first["id"], second["id"]]
    assert body["compatibility"] == {
        "compatible": False,
        "mismatches": {"requested_settings": {"codec": ["HEVC", "AV1"]}},
    }


def test_init_db_migrates_stream_evidence_columns(monkeypatch):
    migration_db = config.DATA_DIR / "migration-stream-evidence.db"
    if migration_db.exists():
        migration_db.unlink()

    conn = sqlite3.connect(migration_db)
    conn.executescript(
        """
        CREATE TABLE sessions (
            id            TEXT PRIMARY KEY,
            name          TEXT,
            status        TEXT NOT NULL DEFAULT 'active',
            host          TEXT,
            client        TEXT,
            network_path  TEXT,
            codec         TEXT,
            resolution    TEXT,
            fps           INTEGER,
            bitrate_mbps  INTEGER,
            hdr           INTEGER NOT NULL DEFAULT 0,
            encoder_settings TEXT,
            outcome       TEXT NOT NULL DEFAULT 'unknown',
            notes         TEXT DEFAULT '',
            diagnosis     TEXT,
            created_at    TEXT NOT NULL,
            started_at    TEXT,
            stopped_at    TEXT
        );
        INSERT INTO sessions (id, status, created_at) VALUES ('legacy', 'active', '2026-01-01T00:00:00Z');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DB_PATH", migration_db)
    hub_db.init_db()
    hub_db.init_db()

    with hub_db.db() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        row = conn.execute("SELECT * FROM sessions WHERE id='legacy'").fetchone()

    got = hub_db.row_to_dict(row)
    assert {
        "comparison_label",
        "apollo_app",
        "game_title",
        "client_role",
        "client_platform",
        "client_version",
        "requested_settings",
        "hdr_details",
        "visual_assessment",
    } <= columns
    assert got["requested_settings"] == {}
    assert got["hdr_details"] == {}
    assert got["visual_assessment"] == {}

    migration_db.unlink()
