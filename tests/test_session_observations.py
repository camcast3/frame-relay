from __future__ import annotations

"""Collector-side log meta and observations payload tests."""

import argparse

from asl_collector import __version__, client, session
from conftest import SAMPLES


def _args(**kw):
    ns = argparse.Namespace(
        source="client",
        role="moonlight",
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


def test_capture_posts_client_log_meta_and_observations(tmp_path, monkeypatch):
    log_path = tmp_path / "Moonlight.log"
    log_path.write_text((SAMPLES / "moonlight-metadata.log").read_text(), encoding="utf-8")

    posted_logs: list[dict] = []
    posted_observations: list[dict] = []

    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr(session.sys, "argv", ["pytest"])
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(client, "post_log",
                        lambda hub, sid, source, role, content, machine=None, meta=None:
                        posted_logs.append({
                            "hub": hub, "sid": sid, "source": source, "role": role,
                            "content": content, "machine": machine, "meta": meta,
                        }))
    monkeypatch.setattr(client, "post_observations",
                        lambda hub, sid, payload: posted_observations.append(payload))
    monkeypatch.setattr(client, "post_links", lambda hub, sid, samples: 0)

    args = _args(source="client", log=[str(log_path)])
    session._capture("http://hub", "s-client", args, "LAPTOP", "moonlight")

    assert len(posted_logs) == 1
    assert posted_logs[0]["meta"] == {
        "platform": "Windows",
        "role": "moonlight",
        "collector_version": __version__,
        "capture_method": "file",
        "capture_path": str(log_path),
    }
    assert posted_observations == [{
        "client_role": "moonlight",
        "client_platform": "Windows",
        "client_version": "6.1.0",
        "requested_settings": {
            "resolution": "2560x1440",
            "fps": 120,
            "bitrate_mbps": 85,
            "codec": "AV1",
            "hdr": True,
        },
        "hdr_details": {
            "requested": True,
            "client_display_hdr": True,
            "client_renderer": "D3D11",
            "client_decoder": "FFmpeg-based",
            "evidence": [
                "Client log: Color coding: HDR (Rec. 2020 + SMPTE 2084 PQ + 10-bit)",
                "[2026-07-23 10:00:04] Qt Warning: HDR fallback to SDR because display does not support it",
            ],
            "encoded_hdr": True,
            "color_primaries": "Rec. 2020",
            "transfer_function": "SMPTE 2084 PQ",
            "bit_depth": 10,
            "tone_mapping": "disabled",
            "status": "fallback",
            "confidence": 0.9,
        },
    }]


def test_capture_posts_host_observations_and_effective_patch(tmp_path, monkeypatch):
    log_path = tmp_path / "sunshine.log"
    log_path.write_text((SAMPLES / "apollo-metadata-rich.log").read_text(), encoding="utf-8")

    posted_logs: list[dict] = []
    posted_observations: list[dict] = []
    patched_sessions: list[dict] = []

    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr(session.sys, "argv", ["pytest"])
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(client, "post_log",
                        lambda hub, sid, source, role, content, machine=None, meta=None:
                        posted_logs.append({"content": content, "meta": meta}))
    monkeypatch.setattr(client, "post_observations",
                        lambda hub, sid, payload: posted_observations.append(payload))
    monkeypatch.setattr(client, "post_links", lambda hub, sid, samples: 0)
    monkeypatch.setattr(client, "post_displays", lambda hub, sid, samples: 0)
    monkeypatch.setattr(client, "get_session", lambda hub, sid: {})
    monkeypatch.setattr(client, "patch_session",
                        lambda hub, sid, fields: patched_sessions.append(fields))
    monkeypatch.setattr(session.displayprobe, "detect", lambda: [])

    args = _args(
        source="host",
        role="apollo",
        log=[str(log_path)],
        comparison_label="AV1 baseline",
        apollo_app="CLI App",
        game_title="CLI Game",
        client_platform="SteamDeck",
        client_version="1.2.3",
    )
    session._capture("http://hub", "s-host", args, "STREAM-HOST", "apollo")

    assert len(posted_logs) == 1
    assert posted_logs[0]["meta"] == {
        "platform": "Windows",
        "role": "apollo",
        "collector_version": __version__,
        "capture_method": "file",
        "capture_path": str(log_path),
    }
    assert posted_observations == [{
        "comparison_label": "AV1 baseline",
        "apollo_app": "CLI App",
        "game_title": "CLI Game",
        "client_platform": "SteamDeck",
        "client_version": "1.2.3",
        "requested_settings": {
            "codec": "AV1",
            "resolution": "3840x2160",
            "fps": 120,
            "bitrate_mbps": 85,
            "hdr": True,
        },
        "hdr_details": {
            "host_display_hdr": True,
            "evidence": [
                "Apollo log: Display is HDR: true",
                "Apollo log: Color coding: HDR (Rec. 2020 + SMPTE 2084 PQ + 10-bit)",
            ],
            "requested": True,
            "encoded_hdr": True,
            "color_primaries": "Rec. 2020",
            "transfer_function": "SMPTE 2084 PQ",
            "bit_depth": 10,
            "confidence": 0.9,
        },
    }]
    assert patched_sessions == [{
        "codec": "AV1",
        "resolution": "3840x2160",
        "fps": 120,
        "bitrate_mbps": 82,
        "hdr": True,
    }]


def test_create_stores_cli_controls_as_requested_not_effective(monkeypatch):
    created: list[dict] = []
    monkeypatch.setattr(session.platform, "system", lambda: "Windows")
    monkeypatch.setattr(client, "create_session",
                        lambda hub, payload: created.append(payload) or "created")
    monkeypatch.setattr(session, "_capture",
                        lambda hub, sid, args, machine, role: f"{hub}/sessions/{sid}")

    args = _args(
        hub_url="http://hub",
        session_id=None,
        create=True,
        attach_latest=False,
        watch=False,
        launch_client=False,
        name="matched HDR",
        role="moonlight",
        source="client",
        codec="AV1",
        resolution="3840x2160",
        fps=120,
        bitrate_mbps=85,
        hdr=True,
        comparison_label="game-hdr",
        apollo_app="Playnite",
        game_title="Game",
    )
    session.run(args)

    assert created == [{
        "name": "matched HDR",
        "client": "TESTBOX",
        "comparison_label": "game-hdr",
        "apollo_app": "Playnite",
        "game_title": "Game",
        "client_role": "moonlight",
        "client_platform": "Windows",
        "requested_settings": {
            "codec": "AV1",
            "resolution": "3840x2160",
            "fps": 120,
            "bitrate_mbps": 85,
            "hdr": True,
        },
    }]
    assert not {"codec", "resolution", "fps", "bitrate_mbps", "hdr"} & created[0].keys()
