from __future__ import annotations

import sqlite3

from hub import config, db as hub_db, service
from hub.models import DisplaySampleIn, SessionCreate


def _create(client, **kw):
    payload = {"name": "display-test", "host": "DOMINO", "client": "couch"}
    payload.update(kw)
    r = client.post("/api/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_display_samples_ingest_orders_and_surfaces_in_bundle(client):
    session = _create(client)
    sid = session["id"]

    r = client.post(
        f"/api/sessions/{sid}/displays",
        json={
            "samples": [
                {
                    "phase": "during",
                    "source": "host",
                    "machine": "DOMINO",
                    "adapter_id": "GPU-0",
                    "adapter_device_path": r"\\?\DISPLAY#GPU0",
                    "source_id": 1,
                    "target_id": 2,
                    "source_name": "DISPLAY1",
                    "friendly_name": "LG OLED",
                    "device_path": r"\\?\DISPLAY#MONITOR0",
                    "is_virtual": False,
                    "primary": True,
                    "width": 2560,
                    "height": 1440,
                    "refresh_hz": 119.98,
                    "rotation": "identity",
                    "scaling": "100%",
                    "output_technology": "HDMI",
                    "hdr_supported": False,
                    "hdr_enabled": True,
                    "bits_per_channel": 10,
                    "color_encoding": "RGB",
                    "sampled_at": "2026-07-23T10:00:01Z",
                },
                {
                    "phase": "before",
                    "friendly_name": "Virtual headless",
                    "is_virtual": True,
                    "sampled_at": "2026-07-23T09:59:59Z",
                },
                {
                    "phase": "during",
                    "friendly_name": "Secondary",
                    "target_id": 3,
                    "sampled_at": "2026-07-23T10:00:01Z",
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"added": 3}

    bundle = client.get(f"/api/sessions/{sid}").json()
    displays = bundle["display_samples"]

    assert bundle["session"]["id"] == sid
    assert [item["friendly_name"] for item in displays] == [
        "Virtual headless",
        "LG OLED",
        "Secondary",
    ]

    before = displays[0]
    assert before["source"] == "host"
    assert before["machine"] is None
    assert before["adapter_id"] is None
    assert before["primary"] is None
    assert before["is_virtual"] == 1
    assert before["sampled_at"] == "2026-07-23T09:59:59Z"

    during = displays[1]
    assert during["session_id"] == sid
    assert during["source"] == "host"
    assert during["machine"] == "DOMINO"
    assert during["phase"] == "during"
    assert during["adapter_id"] == "GPU-0"
    assert during["adapter_device_path"] == r"\\?\DISPLAY#GPU0"
    assert during["source_id"] == 1
    assert during["target_id"] == 2
    assert during["source_name"] == "DISPLAY1"
    assert during["friendly_name"] == "LG OLED"
    assert during["device_path"] == r"\\?\DISPLAY#MONITOR0"
    assert during["is_virtual"] == 0
    assert during["primary"] == 1
    assert during["width"] == 2560
    assert during["height"] == 1440
    assert during["refresh_hz"] == 119.98
    assert during["rotation"] == "identity"
    assert during["scaling"] == "100%"
    assert during["output_technology"] == "HDMI"
    assert during["hdr_supported"] == 0
    assert during["hdr_enabled"] == 1
    assert during["bits_per_channel"] == 10
    assert during["color_encoding"] == "RGB"
    assert during["sampled_at"] == "2026-07-23T10:00:01Z"

    tied = displays[2]
    assert tied["friendly_name"] == "Secondary"
    assert tied["target_id"] == 3
    assert tied["adapter_id"] is None
    assert tied["width"] is None


def test_display_samples_reject_client_source(client):
    session = _create(client)
    response = client.post(
        f"/api/sessions/{session['id']}/displays",
        json={"samples": [{"phase": "during", "source": "client"}]},
    )
    assert response.status_code == 422


def test_display_samples_service_defaults_sampled_at_and_cascade_delete():
    session = service.create_session(
        SessionCreate(name="display-service", host="DOMINO", client="couch")
    )
    sid = session["id"]

    try:
        added = service.add_display_samples(
            sid,
            [
                DisplaySampleIn(
                    phase="before",
                    friendly_name="Earlier",
                    sampled_at="2000-01-01T00:00:00Z",
                ),
                DisplaySampleIn(
                    phase="during",
                    friendly_name="Later",
                    sampled_at="2000-01-01T00:00:01Z",
                ),
                DisplaySampleIn(phase="after", friendly_name="Auto"),
            ],
        )
        assert added == 3

        samples = service.get_display_samples(sid)
        assert [item["friendly_name"] for item in samples] == ["Earlier", "Later", "Auto"]
        assert samples[2]["source"] == "host"
        assert isinstance(samples[2]["sampled_at"], str)
        assert samples[2]["sampled_at"]

        service.delete_session(sid)
        assert service.get_session(sid) is None
        assert service.get_display_samples(sid) == []
    finally:
        service.delete_session(sid)


def test_init_db_creates_display_samples_table_for_existing_db(monkeypatch):
    migration_db = config.DATA_DIR / "migration-display-contract.db"
    if migration_db.exists():
        migration_db.unlink()

    try:
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
            INSERT INTO sessions (id, status, created_at)
            VALUES ('legacy', 'active', '2026-01-01T00:00:00Z');
            """
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(config, "DB_PATH", migration_db)
        hub_db.init_db()
        hub_db.init_db()

        with hub_db.db() as conn:
            columns = {
                row["name"]: row["notnull"]
                for row in conn.execute("PRAGMA table_info(display_samples)").fetchall()
            }
            indexes = {
                row["name"] for row in conn.execute("PRAGMA index_list(display_samples)").fetchall()
            }

        assert {
            "id",
            "session_id",
            "source",
            "machine",
            "phase",
            "adapter_id",
            "adapter_device_path",
            "source_id",
            "target_id",
            "source_name",
            "friendly_name",
            "device_path",
            "is_virtual",
            "primary",
            "width",
            "height",
            "refresh_hz",
            "rotation",
            "scaling",
            "output_technology",
            "hdr_supported",
            "hdr_enabled",
            "bits_per_channel",
            "color_encoding",
            "sampled_at",
        } <= set(columns)
        assert columns["sampled_at"] == 1
        assert "idx_display_samples_session" in indexes
    finally:
        if migration_db.exists():
            migration_db.unlink()
