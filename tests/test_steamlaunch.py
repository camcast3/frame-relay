"""Steam launcher profile and command translation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from asl_collector import client as collector_client
from asl_collector import session, steamlaunch


def test_default_config_path_linux_uses_xdg():
    path = steamlaunch.default_config_path(
        system="Linux",
        env={"XDG_CONFIG_HOME": "/tmp/config"},
        home="/home/tester",
    )
    assert path.as_posix() == "/tmp/config/apollo-streaming-lab/steam-launch.json"


def test_default_config_path_linux_falls_back_to_home():
    path = steamlaunch.default_config_path(system="Linux", env={}, home="/home/tester")
    assert path.as_posix() == (
        "/home/tester/.config/apollo-streaming-lab/steam-launch.json"
    )


def test_default_config_path_windows_uses_localappdata():
    path = steamlaunch.default_config_path(
        system="Windows",
        env={"LOCALAPPDATA": "/users/tester/local"},
        home="/users/tester",
    )
    assert path == Path("/users/tester/local/ApolloStreamingLab/steam-launch.json")


def test_parse_profile_accepts_complete_profile():
    profile = steamlaunch.parse_profile(
        {
            "hub_url": "http://hub:8080/",
            "client_role": "Moonlight",
            "name_template": "{hostname} {client_role} {timestamp}",
            "comparison_label": "example-game-4k120",
            "apollo_app": "Playnite",
            "game_title": "Example Game",
            "network_path": "local-LAN",
            "client_platform": "Bazzite",
            "requested_settings": {
                "codec": "AV1",
                "resolution": "3840x2160",
                "fps": 120,
                "bitrate_mbps": 113,
                "hdr": False,
            },
            "collector": {
                "interval": 10,
                "post_interval": 20,
                "screenshot_poll_interval": 2,
            },
        }
    )

    assert profile.hub_url == "http://hub:8080"
    assert profile.client_role == "moonlight"
    assert profile.fps == 120
    assert profile.bitrate_mbps == 113
    assert profile.hdr is False
    assert profile.interval == 10.0


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "hub_url"),
        ({"hub_url": "hub", "client_role": "moonlight"}, "absolute"),
        ({"hub_url": "http://hub", "client_role": "sunshine"}, "moonlight or artemis"),
        (
            {"hub_url": "http://hub", "client_role": "moonlight", "extra": True},
            "unsupported field",
        ),
        (
            {
                "hub_url": "http://hub",
                "client_role": "moonlight",
                "network_path": "wifi",
            },
            "network_path",
        ),
        (
            {
                "hub_url": "http://hub",
                "client_role": "moonlight",
                "requested_settings": {"fps": True},
            },
            "positive integer",
        ),
        (
            {
                "hub_url": "http://hub",
                "client_role": "moonlight",
                "requested_settings": {"hdr": "false"},
            },
            "true or false",
        ),
        (
            {
                "hub_url": "http://hub",
                "client_role": "moonlight",
                "name_template": "{hostname.__class__}",
            },
            "unsupported name_template field",
        ),
        (
            {
                "hub_url": "http://hub",
                "client_role": "moonlight",
                "collector": {"screenshot_poll_interval": 0},
            },
            "greater than zero",
        ),
    ],
)
def test_parse_profile_rejects_invalid_values(data, message):
    with pytest.raises(steamlaunch.ProfileError, match=message):
        steamlaunch.parse_profile(data)


def test_load_profile_reports_invalid_json(tmp_path):
    path = tmp_path / "steam-launch.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(steamlaunch.ProfileError, match="invalid JSON"):
        steamlaunch.load_profile(path)


def test_render_session_name_uses_only_supported_fields():
    profile = steamlaunch.parse_profile(
        {
            "hub_url": "http://hub",
            "client_role": "artemis",
            "name_template": "{hostname}-{client_role}-{date}-{time}-{timestamp}",
        }
    )
    now = datetime(2026, 8, 26, 13, 20, 30, tzinfo=timezone.utc)

    assert steamlaunch.render_session_name(
        profile, now=now, hostname="minipc"
    ) == "minipc-artemis-2026-08-26-132030-20260826T132030"


def test_parse_profile_rejects_unknown_template_field():
    with pytest.raises(steamlaunch.ProfileError, match="unsupported"):
        steamlaunch.parse_profile(
            {
                "hub_url": "http://hub",
                "client_role": "moonlight",
                "name_template": "{unknown}",
            }
        )


def test_collector_argv_preserves_steam_command_tokens():
    profile = steamlaunch.parse_profile(
        {
            "hub_url": "http://hub:8080",
            "client_role": "moonlight",
            "name_template": "{hostname}",
            "comparison_label": "comparison",
            "requested_settings": {"fps": 120, "hdr": True},
        }
    )

    argv = steamlaunch.collector_argv(
        profile,
        [
            "/usr/bin/flatpak",
            "run",
            "--branch=stable",
            "com.moonlight_stream.Moonlight",
            "argument with spaces",
        ],
        hostname="bazzite",
    )

    assert argv[:8] == [
        "--hub-url",
        "http://hub:8080",
        "--source",
        "client",
        "--role",
        "moonlight",
        "--create",
        "--stop-session",
    ]
    assert "--launch" in argv
    assert argv[argv.index("--launch") + 1] == "/usr/bin/flatpak"
    assert "--launch-arg=run" in argv
    assert "--launch-arg=--branch=stable" in argv
    assert "--launch-arg=argument with spaces" in argv
    assert argv[-1] == "--hdr"


def test_collector_argv_requires_command():
    profile = steamlaunch.parse_profile(
        {"hub_url": "http://hub", "client_role": "moonlight"}
    )

    with pytest.raises(steamlaunch.ProfileError, match="after --"):
        steamlaunch.collector_argv(profile, [])


def test_omitted_hdr_remains_unknown():
    profile = steamlaunch.parse_profile(
        {"hub_url": "http://hub", "client_role": "moonlight"}
    )

    argv = steamlaunch.collector_argv(profile, ["client"], hostname="test")

    assert profile.hdr is None
    assert "--hdr" not in argv
    assert "--no-hdr" not in argv


def test_explicit_sdr_uses_no_hdr_flag():
    profile = steamlaunch.parse_profile(
        {
            "hub_url": "http://hub",
            "client_role": "moonlight",
            "requested_settings": {"hdr": False},
        }
    )

    argv = steamlaunch.collector_argv(profile, ["client"], hostname="test")

    assert argv[-1] == "--no-hdr"
    parsed = session.build_parser().parse_args(argv)
    assert parsed.hdr is False


def test_main_loads_config_and_delegates_to_session(tmp_path, monkeypatch):
    path = tmp_path / "steam-launch.json"
    path.write_text(
        json.dumps({"hub_url": "http://hub", "client_role": "artemis"}),
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(
        steamlaunch.session,
        "main",
        lambda argv: captured.setdefault("argv", argv),
    )

    steamlaunch.main(["--config", str(path), "--", "client.exe", "--fullscreen"])

    assert "--role" in captured["argv"]
    assert captured["argv"][captured["argv"].index("--role") + 1] == "artemis"
    assert "--launch-arg=--fullscreen" in captured["argv"]


def test_main_writes_headless_output_to_local_log(tmp_path, monkeypatch):
    config = tmp_path / "steam-launch.json"
    log = tmp_path / "state" / "steam-launch.log"
    config.write_text(
        json.dumps({"hub_url": "http://hub", "client_role": "moonlight"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(steamlaunch.session, "main", lambda argv: print("collector ran"))

    steamlaunch.main(
        [
            "--config",
            str(config),
            "--log-file",
            str(log),
            "--",
            "client",
        ]
    )

    text = log.read_text(encoding="utf-8")
    assert "Steam launch started" in text
    assert "collector ran" in text


def test_rotate_log_keeps_one_backup(tmp_path):
    log = tmp_path / "steam-launch.log"
    log.write_text("12345", encoding="utf-8")

    steamlaunch._rotate_log(log, max_bytes=5)

    assert not log.exists()
    assert log.with_name("steam-launch.log.1").read_text(encoding="utf-8") == "12345"


def test_created_session_is_stopped_when_client_launch_fails(monkeypatch):
    stopped = []
    created = []

    def create_session(hub, payload):
        created.append(payload)
        return "created-session"

    monkeypatch.setattr(collector_client, "create_session", create_session)
    monkeypatch.setattr(
        collector_client, "stop_session", lambda hub, sid: stopped.append((hub, sid))
    )
    monkeypatch.setattr(
        session.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("not executable")),
    )
    args = session.build_parser().parse_args(
        [
            "--hub-url",
            "http://hub",
            "--source",
            "client",
            "--role",
            "moonlight",
            "--create",
            "--launch",
            "missing-client",
        ]
    )

    with pytest.raises(SystemExit, match="failed to launch"):
        session.run(args)

    assert stopped == [("http://hub", "created-session")]
    assert created[0]["requested_settings"] == {}


def test_attached_session_is_not_stopped_when_client_launch_fails(monkeypatch):
    stopped = []
    monkeypatch.setattr(
        collector_client, "stop_session", lambda hub, sid: stopped.append((hub, sid))
    )
    monkeypatch.setattr(
        session.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("not executable")),
    )
    args = session.build_parser().parse_args(
        [
            "--hub-url",
            "http://hub",
            "--source",
            "client",
            "--role",
            "moonlight",
            "--session-id",
            "existing-session",
            "--launch",
            "missing-client",
        ]
    )

    with pytest.raises(SystemExit, match="failed to launch"):
        session.run(args)

    assert stopped == []
