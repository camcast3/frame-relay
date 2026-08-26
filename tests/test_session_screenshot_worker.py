from __future__ import annotations

import argparse
import binascii
import zlib

from asl_collector import client, session


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


def _args(**overrides):
    ns = argparse.Namespace(
        source="client",
        role="moonlight",
        log=[],
        launch=None,
        launch_arg=[],
        machine="TESTBOX",
        interval=0.0,
        post_interval=0.0,
        screenshot_token="secret-token",
        screenshot_poll_interval=1.5,
        duration=0,
        stop_session=False,
        apollo_port=47989,
        wg_subnet=[],
        host=None,
        client=None,
        network_path=None,
        codec=None,
        resolution=None,
        fps=None,
        bitrate_mbps=None,
        hdr=False,
        comparison_label=None,
        apollo_app=None,
        game_title=None,
        client_platform=None,
        client_version=None,
        watch_interval=0.01,
    )
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


class _LoopEvent:
    def __init__(self, wait_results):
        self.wait_results = list(wait_results)
        self.timeouts: list[float] = []

    def is_set(self):
        return False

    def wait(self, timeout):
        self.timeouts.append(timeout)
        return self.wait_results.pop(0)


def test_build_parser_uses_env_screenshot_token_default(monkeypatch):
    monkeypatch.setenv("ASL_SCREENSHOT_TOKEN", "env-screenshot-token")

    args = session.build_parser().parse_args(["--hub-url", "http://hub"])

    assert args.screenshot_token == "env-screenshot-token"
    assert args.screenshot_poll_interval == 3


def test_start_screenshot_worker_skips_when_token_missing():
    assert session._start_screenshot_worker(
        "http://hub",
        "sid",
        "host",
        "STREAM-HOST",
        "",
        3.0,
        _LoopEvent([True]),
    ) is None


def test_start_screenshot_worker_normalizes_token_whitespace(monkeypatch):
    captured: dict[str, object] = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(session.threading, "Thread", FakeThread)
    worker = session._start_screenshot_worker(
        "http://hub",
        "sid",
        "host",
        "STREAM-HOST",
        " token with spaces ",
        3.0,
        _LoopEvent([True]),
    )
    assert worker is not None
    assert captured["args"][4] == "token with spaces"


def test_screenshot_worker_processes_each_request_once_and_cleans_up(tmp_path, monkeypatch):
    capture_path = tmp_path / "capture.png"
    calls: dict[str, list[tuple]] = {"pending": [], "complete": []}
    pending_batches = iter([[{"id": 7}], [{"id": 7}]])

    monkeypatch.setattr(
        client,
        "pending_screenshot_requests",
        lambda hub, sid, source, token=None: calls["pending"].append((hub, sid, source, token))
        or next(pending_batches),
    )

    def fake_capture(_preferred_display=None):
        capture_path.write_bytes(_png_bytes(8, 6))
        return {
            "path": str(capture_path),
            "display_name": "Desktop",
            "width": 8,
            "height": 6,
            "captured_at": "2026-08-13T12:00:00Z",
        }

    monkeypatch.setattr(session.screenshot, "capture", fake_capture)
    monkeypatch.setattr(
        client,
        "complete_screenshot_request",
        lambda hub, sid, request_id, source, path, **kw: calls["complete"].append(
            (hub, sid, request_id, source, path, kw)
        )
        or {"status": "completed"},
    )
    monkeypatch.setattr(
        client,
        "fail_screenshot_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not fail")),
    )

    stop_evt = _LoopEvent([False, True])
    session._screenshot_worker_loop(
        "http://hub",
        "session-1",
        "host",
        "STREAM-HOST",
        "secret-token",
        0.25,
        stop_evt,
    )

    assert calls["pending"] == [
        ("http://hub", "session-1", "host", "secret-token"),
        ("http://hub", "session-1", "host", "secret-token"),
    ]
    assert len(calls["complete"]) == 1
    assert calls["complete"][0][2] == 7
    assert calls["complete"][0][3] == "host"
    assert calls["complete"][0][5]["token"] == "secret-token"
    assert calls["complete"][0][5]["machine"] == "STREAM-HOST"
    assert not capture_path.exists()
    assert stop_evt.timeouts == [0.25, 0.25]


def test_process_screenshot_request_reports_failures_and_cleans_up(tmp_path, monkeypatch):
    capture_path = tmp_path / "failed.png"
    failures: list[tuple] = []

    def fake_capture(_preferred_display=None):
        capture_path.write_bytes(_png_bytes(4, 4))
        return {
            "path": str(capture_path),
            "display_name": "Desktop",
            "width": 4,
            "height": 4,
            "captured_at": "2026-08-13T12:00:00Z",
        }

    monkeypatch.setattr(session.screenshot, "capture", fake_capture)
    monkeypatch.setattr(
        client,
        "complete_screenshot_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("upload failed")),
    )
    monkeypatch.setattr(
        client,
        "fail_screenshot_request",
        lambda hub, sid, request_id, source, error, **kw: failures.append(
            (hub, sid, request_id, source, error, kw)
        )
        or {"status": "failed"},
    )

    session._process_screenshot_request(
        "http://hub",
        "session-2",
        22,
        "client",
        "couch",
        "secret-token",
    )

    assert failures == [
        (
            "http://hub",
            "session-2",
            22,
            "client",
            "upload failed",
            {"machine": "couch", "token": "secret-token"},
        )
    ]
    assert not capture_path.exists()


def test_screenshot_worker_retries_when_no_terminal_state_was_accepted(monkeypatch):
    pending_batches = iter([[{"id": 33}], [{"id": 33}]])
    processed: list[int] = []

    monkeypatch.setattr(
        client,
        "pending_screenshot_requests",
        lambda *args, **kwargs: next(pending_batches),
    )

    def fake_process(hub, sid, request_id, source, machine, token):
        processed.append(request_id)
        return len(processed) > 1

    monkeypatch.setattr(session, "_process_screenshot_request", fake_process)
    session._screenshot_worker_loop(
        "http://hub",
        "session-retry",
        "host",
        "STREAM-HOST",
        "secret-token",
        0.25,
        _LoopEvent([False, True]),
    )
    assert processed == [33, 33]


def test_host_screenshot_prefers_active_virtual_display(monkeypatch):
    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        session.displayprobe,
        "detect",
        lambda: [
            {"source_name": r"\\.\DISPLAY1", "primary": True, "is_virtual": False},
            {"source_name": r"\\.\DISPLAY2", "primary": False, "is_virtual": True},
        ],
    )
    assert session._preferred_screenshot_display("host") == r"\\.\DISPLAY2"
    assert session._preferred_screenshot_display("client") is None


def test_capture_joins_screenshot_worker_on_teardown(tmp_path, monkeypatch):
    log_path = tmp_path / "moonlight.log"
    log_path.write_text("Moonlight log line\n", encoding="utf-8")

    class FakeWorker:
        def __init__(self):
            self.join_timeout = None

        def join(self, timeout=None):
            self.join_timeout = timeout

    worker = FakeWorker()

    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(session, "_start_screenshot_worker", lambda *args, **kwargs: worker)
    monkeypatch.setattr(client, "post_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_links", lambda *args, **kwargs: 0)
    monkeypatch.setattr(client, "post_observations", lambda *args, **kwargs: None)

    session._capture(
        "http://hub",
        "session-3",
        _args(log=[str(log_path)], screenshot_poll_interval=1.75),
        "couch",
        "moonlight",
    )

    assert worker.join_timeout == 6.75
