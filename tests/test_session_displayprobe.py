from __future__ import annotations

import argparse
import copy

from asl_collector import client, session


def _args(**kw):
    ns = argparse.Namespace(
        source="host",
        role="apollo",
        log=[],
        launch=None,
        launch_arg=[],
        machine="TESTBOX",
        interval=0.0,
        post_interval=0.0,
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
    for key, value in kw.items():
        setattr(ns, key, value)
    return ns


def _display_sample(
    *,
    adapter_id: str,
    source_id: int,
    target_id: int,
    source_name: str,
    friendly_name: str,
    device_path: str,
    adapter_device_path: str,
    width: int,
    height: int,
    refresh_hz: int,
    is_virtual: bool | None,
    sampled_at: str,
) -> list[dict]:
    return [{
        "source": "host",
        "machine": None,
        "phase": None,
        "adapter_id": adapter_id,
        "adapter_device_path": adapter_device_path,
        "source_id": source_id,
        "target_id": target_id,
        "source_name": source_name,
        "friendly_name": friendly_name,
        "device_path": device_path,
        "is_virtual": is_virtual,
        "primary": True,
        "width": width,
        "height": height,
        "refresh_hz": refresh_hz,
        "rotation": "identity",
        "scaling": "preferred",
        "output_technology": "indirect-virtual" if is_virtual else "hdmi",
        "hdr_supported": True,
        "hdr_enabled": True,
        "bits_per_channel": 10,
        "color_encoding": "rgb",
        "sampled_at": sampled_at,
    }]


def test_host_capture_posts_before_during_after_displays_and_dedups(tmp_path, monkeypatch):
    log_path = tmp_path / "sunshine.log"
    log_path.write_text("Apollo log line\n", encoding="utf-8")

    posted_display_batches: list[list[dict]] = []

    class FakeEvent:
        def __init__(self):
            self._set = False
            self._wait_calls = 0

        def wait(self, _timeout=None):
            if self._set:
                return True
            self._wait_calls += 1
            return self._wait_calls > 2

        def set(self):
            self._set = True

    class ImmediateThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

        def join(self, timeout=None):
            return None

    snapshots = iter([
        _display_sample(
            adapter_id="00000000:00000001",
            source_id=0,
            target_id=10,
            source_name=r"\\.\DISPLAY1",
            friendly_name="Sunshine Virtual Display",
            device_path=r"ROOT\SunshineVirtualDisplay\0000",
            adapter_device_path=r"\\?\DISPLAY#Sunshine#0001",
            width=3840,
            height=2160,
            refresh_hz=144,
            is_virtual=True,
            sampled_at="2026-08-13T19:00:00Z",
        ),
        _display_sample(
            adapter_id="00000000:00000001",
            source_id=0,
            target_id=10,
            source_name=r"\\.\DISPLAY1",
            friendly_name="Sunshine Virtual Display",
            device_path=r"ROOT\SunshineVirtualDisplay\0000",
            adapter_device_path=r"\\?\DISPLAY#Sunshine#0001",
            width=3840,
            height=2160,
            refresh_hz=144,
            is_virtual=True,
            sampled_at="2026-08-13T19:00:05Z",
        ),
        _display_sample(
            adapter_id="00000000:00000001",
            source_id=0,
            target_id=10,
            source_name=r"\\.\DISPLAY1",
            friendly_name="Sunshine Virtual Display",
            device_path=r"ROOT\SunshineVirtualDisplay\0000",
            adapter_device_path=r"\\?\DISPLAY#Sunshine#0001",
            width=3840,
            height=2160,
            refresh_hz=144,
            is_virtual=True,
            sampled_at="2026-08-13T19:00:10Z",
        ),
        _display_sample(
            adapter_id="00000000:00000001",
            source_id=0,
            target_id=10,
            source_name=r"\\.\DISPLAY1",
            friendly_name="Sunshine Virtual Display",
            device_path=r"ROOT\SunshineVirtualDisplay\0000",
            adapter_device_path=r"\\?\DISPLAY#Sunshine#0001",
            width=2560,
            height=1440,
            refresh_hz=120,
            is_virtual=True,
            sampled_at="2026-08-13T19:00:15Z",
        ),
        _display_sample(
            adapter_id="00000000:00000001",
            source_id=0,
            target_id=10,
            source_name=r"\\.\DISPLAY1",
            friendly_name="Sunshine Virtual Display",
            device_path=r"ROOT\SunshineVirtualDisplay\0000",
            adapter_device_path=r"\\?\DISPLAY#Sunshine#0001",
            width=2560,
            height=1440,
            refresh_hz=120,
            is_virtual=True,
            sampled_at="2026-08-13T19:00:20Z",
        ),
    ])

    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr(session.sys, "argv", ["pytest"])
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(session.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(session.threading, "Event", FakeEvent)
    monkeypatch.setattr(session.displayprobe, "detect", lambda: copy.deepcopy(next(snapshots)))
    monkeypatch.setattr(client, "post_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_links", lambda *args, **kwargs: 0)
    monkeypatch.setattr(client, "post_observations", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "get_session", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "patch_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        client,
        "post_displays",
        lambda hub, sid, samples: posted_display_batches.append(copy.deepcopy(samples)) or len(samples),
    )

    args = _args(log=[str(log_path)], post_interval=0.01)
    session._capture("http://hub", "s-host", args, "STREAM-HOST", "apollo")

    assert [sample["phase"] for sample in posted_display_batches[0]] == ["before", "during"]
    assert [sample["phase"] for sample in posted_display_batches[1]] == ["during"]
    assert [sample["phase"] for sample in posted_display_batches[2]] == ["after"]
    assert len(posted_display_batches) == 3
    assert all(sample["machine"] == "STREAM-HOST" for batch in posted_display_batches for sample in batch)
    assert posted_display_batches[0][0]["width"] == 3840
    assert posted_display_batches[1][0]["width"] == 2560
    assert posted_display_batches[2][0]["width"] == 2560


def test_host_capture_skips_display_probe_off_windows(tmp_path, monkeypatch):
    log_path = tmp_path / "sunshine.log"
    log_path.write_text("Apollo log line\n", encoding="utf-8")

    monkeypatch.setattr(session.platform, "system", lambda: "Linux")
    monkeypatch.setattr(session.sys, "argv", ["pytest"])
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(client, "post_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_links", lambda *args, **kwargs: 0)
    monkeypatch.setattr(client, "post_observations", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "get_session", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "patch_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        client,
        "post_displays",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not post displays")),
    )
    monkeypatch.setattr(
        session.displayprobe,
        "detect",
        lambda: (_ for _ in ()).throw(AssertionError("should not probe displays")),
    )

    args = _args(log=[str(log_path)])
    session._capture("http://hub", "s-linux", args, "DECK", "apollo")


def test_short_capture_records_true_during_snapshot_before_teardown(tmp_path, monkeypatch):
    log_path = tmp_path / "sunshine.log"
    log_path.write_text("Apollo log line\n", encoding="utf-8")
    posted: list[list[dict]] = []
    snapshots = iter([
        _display_sample(
            adapter_id="0:1", source_id=0, target_id=1, source_name="DISPLAY1",
            friendly_name="Physical", device_path="physical", adapter_device_path="gpu",
            width=1920, height=1080, refresh_hz=60, is_virtual=False,
            sampled_at="2026-08-13T19:00:00Z",
        ),
        _display_sample(
            adapter_id="0:1", source_id=1, target_id=2, source_name="DISPLAY2",
            friendly_name="Apollo Virtual Display", device_path="apollo", adapter_device_path="gpu",
            width=3840, height=2160, refresh_hz=120, is_virtual=True,
            sampled_at="2026-08-13T19:00:01Z",
        ),
        _display_sample(
            adapter_id="0:1", source_id=0, target_id=1, source_name="DISPLAY1",
            friendly_name="Physical", device_path="physical", adapter_device_path="gpu",
            width=1920, height=1080, refresh_hz=60, is_virtual=False,
            sampled_at="2026-08-13T19:00:02Z",
        ),
    ])
    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(session.displayprobe, "detect", lambda: copy.deepcopy(next(snapshots)))
    monkeypatch.setattr(client, "post_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_links", lambda *args, **kwargs: 0)
    monkeypatch.setattr(client, "post_observations", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_displays",
                        lambda hub, sid, rows: posted.append(copy.deepcopy(rows)) or len(rows))
    monkeypatch.setattr(client, "get_session", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "patch_session", lambda *args, **kwargs: None)

    session._capture(
        "http://hub", "short", _args(log=[str(log_path)], post_interval=0),
        "STREAM-HOST", "apollo",
    )

    assert [[row["phase"] for row in batch] for batch in posted] == [
        ["before", "during"], ["after"],
    ]
    during = posted[0][1]
    assert during["friendly_name"] == "Apollo Virtual Display"
    assert during["width"] == 3840


def test_watch_capture_omits_unreliable_before_baseline(tmp_path, monkeypatch):
    log_path = tmp_path / "sunshine.log"
    log_path.write_text("Apollo log line\n", encoding="utf-8")
    posted: list[list[dict]] = []
    snapshots = iter([
        _display_sample(
            adapter_id="0:1", source_id=1, target_id=2, source_name="DISPLAY2",
            friendly_name="Apollo Virtual Display", device_path="apollo", adapter_device_path="gpu",
            width=3840, height=2160, refresh_hz=120, is_virtual=True,
            sampled_at="2026-08-13T19:00:01Z",
        ),
        _display_sample(
            adapter_id="0:1", source_id=0, target_id=1, source_name="DISPLAY1",
            friendly_name="Physical", device_path="physical", adapter_device_path="gpu",
            width=1920, height=1080, refresh_hz=60, is_virtual=False,
            sampled_at="2026-08-13T19:00:02Z",
        ),
    ])
    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr(session.displayprobe, "detect", lambda: copy.deepcopy(next(snapshots)))
    monkeypatch.setattr(session, "_session_started_at", lambda *args: None)
    monkeypatch.setattr(session, "_session_ended", lambda *args: True)
    monkeypatch.setattr(client, "post_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_links", lambda *args, **kwargs: 0)
    monkeypatch.setattr(client, "post_observations", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "post_displays",
                        lambda hub, sid, rows: posted.append(copy.deepcopy(rows)) or len(rows))
    monkeypatch.setattr(client, "get_session", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "patch_session", lambda *args, **kwargs: None)

    session._capture(
        "http://hub", "watched",
        _args(log=[str(log_path)], post_interval=0, watch_interval=0),
        "STREAM-HOST", "apollo", watch=True,
    )

    phases = [row["phase"] for batch in posted for row in batch]
    assert phases == ["during", "after"]
