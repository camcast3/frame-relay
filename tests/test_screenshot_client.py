from __future__ import annotations

import binascii
import json
import zlib

from asl_collector import client


class _DummyResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def _png_bytes(width: int, height: int) -> bytes:
    def _chunk(kind: bytes, payload: bytes) -> bytes:
        crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + crc.to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    row = b"\x00" + (b"\x00\x00\x00\xFF" * width)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(row * height))
        + _chunk(b"IEND", b"")
    )


def _headers(req) -> dict[str, str]:
    return {key.lower(): value for key, value in req.header_items()}


def test_pending_screenshot_requests_sends_source_query_and_auth(monkeypatch):
    seen: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["headers"] = _headers(req)
        seen["timeout"] = timeout
        return _DummyResponse('[{"id": 1}]')

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    pending = client.pending_screenshot_requests(
        "http://hub",
        "session-1",
        "host",
        token="secret-token",
    )

    assert pending == [{"id": 1}]
    assert seen["url"] == "http://hub/api/sessions/session-1/screenshot-requests/pending?source=host"
    assert seen["headers"]["x-asl-screenshot-token"] == "secret-token"
    assert seen["timeout"] == 30


def test_screenshot_token_whitespace_is_normalized(monkeypatch):
    seen: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        seen["headers"] = _headers(req)
        return _DummyResponse("[]")

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    client.pending_screenshot_requests(
        "http://hub",
        "session-1",
        "host",
        token=" token with spaces ",
    )
    assert seen["headers"]["x-asl-screenshot-token"] == "token with spaces"


def test_complete_screenshot_request_uses_stdlib_multipart_and_auth(tmp_path, monkeypatch):
    capture = tmp_path / "capture.png"
    capture.write_bytes(_png_bytes(4, 3))
    seen: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["headers"] = _headers(req)
        seen["body"] = req.data
        seen["timeout"] = timeout
        return _DummyResponse('{"status":"completed"}')

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    result = client.complete_screenshot_request(
        "http://hub",
        "session-2",
        99,
        "client",
        str(capture),
        machine="couch",
        captured_at="2026-08-13T12:00:00Z",
        display_name="Desktop",
        token="secret-token",
    )

    body = seen["body"]
    assert result == {"status": "completed"}
    assert seen["url"] == "http://hub/api/sessions/session-2/screenshot-requests/99/complete"
    assert seen["headers"]["x-asl-screenshot-token"] == "secret-token"
    assert seen["headers"]["content-type"].startswith("multipart/form-data; boundary=")
    assert seen["timeout"] == 30
    assert b'name="source"' in body
    assert b"client" in body
    assert b'name="machine"' in body
    assert b"couch" in body
    assert b'name="captured_at"' in body
    assert b"2026-08-13T12:00:00Z" in body
    assert b'name="display_name"' in body
    assert b"Desktop" in body
    assert b'filename="capture.png"' in body
    assert _png_bytes(4, 3) in body


def test_existing_json_requests_still_post_application_json(monkeypatch):
    seen: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["headers"] = _headers(req)
        seen["body"] = req.data
        seen["timeout"] = timeout
        return _DummyResponse("")

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    client.post_log("http://hub", "session-3", "host", "apollo", "hello", machine="STREAM-HOST")

    assert seen["url"] == "http://hub/api/sessions/session-3/logs"
    assert seen["headers"]["content-type"] == "application/json"
    assert json.loads(seen["body"].decode("utf-8")) == {
        "source": "host",
        "role": "apollo",
        "content": "hello",
        "machine": "STREAM-HOST",
    }
    assert seen["timeout"] == 30
