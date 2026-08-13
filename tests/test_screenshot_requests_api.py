"""Targeted API tests for authenticated screenshot requests."""
from __future__ import annotations

from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
import threading

from hub import config, db as hub_db, service

PNG_BYTES = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV7kAAAAASUVORK5CYII="
)


def _create(client, **overrides):
    payload = {
        "name": "screenshot-test",
        "host": "DOMINO",
        "client": "couch",
        "network_path": "local-LAN",
    }
    payload.update(overrides)
    response = client.post("/api/sessions", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str | None = None) -> dict[str, str]:
    return {"X-ASL-Screenshot-Token": token or config.SCREENSHOT_TOKEN}


def _request_artifacts(session_id: str) -> list[str]:
    return sorted(path.name for path in config.ARTIFACTS_DIR.glob(f"{session_id}_request_*.png"))


def test_screenshot_requests_require_enabled_valid_token(client, monkeypatch):
    session = _create(client)
    sid = session["id"]

    monkeypatch.setattr(config, "SCREENSHOT_TOKEN", "")
    disabled = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={},
        headers=_auth("ignored"),
    )
    assert disabled.status_code == 503

    monkeypatch.setattr(config, "SCREENSHOT_TOKEN", "expected-token")
    missing = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "host"},
    )
    wrong = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={},
        headers=_auth("wrong-token"),
    )
    padded = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={},
        headers=_auth(" expected-token "),
    )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert padded.status_code == 401

    monkeypatch.setattr(config, "SCREENSHOT_TOKEN", " expected-token ")
    stripped = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "host"},
        headers=_auth("expected-token"),
    )
    exact = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "host"},
        headers=_auth(" expected-token "),
    )
    assert stripped.status_code == 401
    assert exact.status_code == 200


def test_queue_screenshot_requests_deduplicates_and_rejects_invalid_states(client):
    active = _create(client, name="active-screenshot")
    stopped = _create(client, name="stopped-screenshot")
    client.post(f"/api/sessions/{stopped['id']}/stop")

    empty = client.post(
        f"/api/sessions/{active['id']}/screenshot-requests",
        json={"targets": []},
        headers=_auth(),
    )
    assert empty.status_code == 422

    queued = client.post(
        f"/api/sessions/{active['id']}/screenshot-requests",
        json={"targets": ["host", "host", "client"]},
        headers=_auth(),
    )
    assert queued.status_code == 200, queued.text
    body = queued.json()
    assert [item["target_source"] for item in body] == ["host", "client"]
    assert all(item["status"] == "pending" for item in body)
    assert all(item["artifact_filename"] is None for item in body)

    stopped_response = client.post(
        f"/api/sessions/{stopped['id']}/screenshot-requests",
        json={},
        headers=_auth(),
    )
    assert stopped_response.status_code == 409


def test_pending_screenshot_requests_are_source_isolated(client):
    session = _create(client, name="source-isolated")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={},
        headers=_auth(),
    )
    assert queued.status_code == 200, queued.text
    assert [item["target_source"] for item in queued.json()] == ["host", "client"]

    host_pending = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "host"},
        headers=_auth(),
    )
    client_pending = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "client"},
        headers=_auth(),
    )

    assert [item["target_source"] for item in host_pending.json()] == ["host"]
    assert [item["target_source"] for item in client_pending.json()] == ["client"]


def test_complete_screenshot_request_creates_artifact_and_enriches_bundle(client):
    session = _create(client, name="complete-screenshot")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]

    wrong_source = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={"source": "client"},
        files={"file": ("..\\nested/capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert wrong_source.status_code == 409

    with hub_db.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE session_id=?",
            (sid,),
        ).fetchone()[0] == 0
    assert _request_artifacts(sid) == []

    completed = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={
            "source": "host",
            "machine": "DOMINO",
            "captured_at": "2026-08-13T12:00:00Z",
            "display_name": "Moonlight Monitor",
        },
        files={"file": ("..\\nested/capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()

    assert body["status"] == "completed"
    assert body["target_source"] == "host"
    assert body["machine"] == "DOMINO"
    assert body["completed_at"] == "2026-08-13T12:00:00Z"
    assert body["artifact_id"] is not None
    assert body["artifact_kind"] == "requested_host_screenshot"
    assert body["artifact_filename"].endswith(".png")
    assert "\\" not in body["artifact_filename"]
    assert "/" not in body["artifact_filename"]
    assert "host" in body["artifact_caption"]
    assert "Moonlight Monitor" in body["artifact_caption"]
    assert "2026-08-13T12:00:00Z" in body["artifact_caption"]

    artifact_path = config.ARTIFACTS_DIR / body["artifact_filename"]
    assert artifact_path.exists()
    assert artifact_path.read_bytes() == PNG_BYTES

    duplicate = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={"source": "host"},
        files={"file": ("capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert duplicate.status_code == 409
    assert _request_artifacts(sid) == [body["artifact_filename"]]

    bundle = client.get(f"/api/sessions/{sid}")
    assert bundle.status_code == 200, bundle.text
    screenshot_request = bundle.json()["screenshot_requests"][0]
    assert screenshot_request["id"] == request_id
    assert screenshot_request["artifact_filename"] == body["artifact_filename"]
    assert bundle.json()["artifacts"][0]["filename"] == body["artifact_filename"]


def test_complete_screenshot_request_is_atomic_under_race(client):
    session = _create(client, name="atomic-completion")
    sid = session["id"]
    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]
    barrier = threading.Barrier(2)

    def complete(filename: str) -> str:
        barrier.wait()
        try:
            service.complete_screenshot_request(
                session_id=sid,
                request_id=request_id,
                source="host",
                filename=filename,
                machine="DOMINO",
                caption=filename,
                kind="requested_host_screenshot",
            )
            return "completed"
        except service.ScreenshotRequestConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(complete, ["first.png", "second.png"]))

    assert outcomes == ["completed", "conflict"]
    with hub_db.db() as conn:
        artifacts = conn.execute(
            "SELECT filename FROM artifacts WHERE session_id=?",
            (sid,),
        ).fetchall()
        request = conn.execute(
            "SELECT status, artifact_id FROM screenshot_requests WHERE id=?",
            (request_id,),
        ).fetchone()
    assert len(artifacts) == 1
    assert request["status"] == "completed"
    assert request["artifact_id"] is not None


def test_complete_screenshot_request_cleanup_is_best_effort_on_conflict(client, monkeypatch):
    session = _create(client, name="cleanup-best-effort")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]

    path_type = type(config.ARTIFACTS_DIR)
    original_unlink = path_type.unlink

    def broken_unlink(self, *args, **kwargs):
        if self.name.startswith(f"{sid}_request_{request_id}_"):
            raise OSError("locked")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(path_type, "unlink", broken_unlink)

    conflict = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={"source": "client"},
        files={"file": ("capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert conflict.status_code == 409

    with hub_db.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE session_id=?",
            (sid,),
        ).fetchone()[0] == 0

    pending = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "host"},
        headers=_auth(),
    )
    assert pending.status_code == 200, pending.text
    assert [item["id"] for item in pending.json()] == [request_id]


def test_complete_screenshot_request_rejects_oversized_uploads_without_artifacts(client, monkeypatch):
    session = _create(client, name="oversized-screenshot")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]

    monkeypatch.setattr(config, "SCREENSHOT_MAX_UPLOAD_BYTES", len(PNG_BYTES) - 1)
    oversized = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={"source": "host"},
        files={"file": ("capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert oversized.status_code == 413

    with hub_db.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE session_id=?",
            (sid,),
        ).fetchone()[0] == 0
    assert _request_artifacts(sid) == []

    pending = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "host"},
        headers=_auth(),
    )
    assert pending.status_code == 200, pending.text
    assert [item["id"] for item in pending.json()] == [request_id]


def test_fail_screenshot_request_marks_request_and_clears_pending(client):
    session = _create(client, name="fail-screenshot")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["client"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]

    failed = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/fail",
        json={"source": "client", "error": "capture timed out", "machine": "couch"},
        headers=_auth(),
    )
    assert failed.status_code == 200, failed.text
    body = failed.json()

    assert body["status"] == "failed"
    assert body["error"] == "capture timed out"
    assert body["machine"] == "couch"
    assert body["completed_at"]
    assert body["artifact_id"] is None
    assert body["artifact_filename"] is None

    duplicate = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/fail",
        json={"source": "client", "error": "capture timed out", "machine": "couch"},
        headers=_auth(),
    )
    assert duplicate.status_code == 409

    pending = client.get(
        f"/api/sessions/{sid}/screenshot-requests/pending",
        params={"source": "client"},
        headers=_auth(),
    )
    assert pending.status_code == 200, pending.text
    assert pending.json() == []

    bundle = client.get(f"/api/sessions/{sid}").json()
    assert bundle["screenshot_requests"][0]["status"] == "failed"


def test_fail_screenshot_request_bounds_error_storage(client):
    session = _create(client, name="bounded-fail-screenshot")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["client"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]

    error = f"  {'x' * 2100}\n"
    failed = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/fail",
        json={"source": "client", "error": error, "machine": "couch"},
        headers=_auth(),
    )
    assert failed.status_code == 200, failed.text
    body = failed.json()

    expected_error = "x" * 2000
    assert body["error"] == expected_error
    assert len(body["error"]) == 2000

    bundle = client.get(f"/api/sessions/{sid}")
    assert bundle.status_code == 200, bundle.text
    assert bundle.json()["screenshot_requests"][0]["error"] == expected_error


def test_screenshot_requests_cascade_with_session_delete(client):
    session = _create(client, name="cascade-screenshot")
    sid = session["id"]

    queued = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    request_id = queued.json()[0]["id"]

    completed = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={"source": "host"},
        files={"file": ("capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert completed.status_code == 200, completed.text

    deleted = client.delete(f"/api/sessions/{sid}")
    assert deleted.status_code == 200, deleted.text

    with hub_db.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM screenshot_requests WHERE session_id=?",
            (sid,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE session_id=?",
            (sid,),
        ).fetchone()[0] == 0
