"""Cross-platform Steam wrapper installation and artwork mapping."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from frame_relay_collector import steamsetup

ROOT = Path(__file__).resolve().parent.parent


def _cstring(value: str) -> bytes:
    return value.encode() + b"\x00"


def _vdf_string(key: str, value: str) -> bytes:
    return b"\x01" + _cstring(key) + _cstring(value)


def _vdf_int(key: str, value: int) -> bytes:
    return b"\x02" + _cstring(key) + struct.pack("<i", value)


def _vdf_object(key: str, content: bytes) -> bytes:
    return b"\x00" + _cstring(key) + content + b"\x08"


def _shortcuts_vdf(entries: list[tuple[int, str, str, str]]) -> bytes:
    content = b""
    for index, (appid, appname, exe, launch_options) in enumerate(entries):
        entry = (
            _vdf_int("appid", appid)
            + _vdf_string("AppName", appname)
            + _vdf_string("Exe", exe)
            + _vdf_string("LaunchOptions", launch_options)
        )
        content += _vdf_object(str(index), entry)
    return _vdf_object("shortcuts", content) + b"\x08"


def test_install_paths_linux_uses_xdg(tmp_path):
    paths = steamsetup.install_paths(
        system="Linux",
        env={
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_BIN_HOME": str(tmp_path / "bin"),
        },
        home=str(tmp_path / "home"),
    )

    assert paths.config_path == (
        tmp_path / "config" / "frame-relay" / "steam-launch.json"
    )
    assert paths.data_root == tmp_path / "data" / "frame-relay"
    assert paths.state_root == tmp_path / "state" / "frame-relay"
    assert paths.launcher_path == tmp_path / "bin" / "frame-relay-steam-launch"


def test_install_paths_windows_uses_localappdata(tmp_path):
    paths = steamsetup.install_paths(
        system="Windows",
        env={"LOCALAPPDATA": str(tmp_path / "Local")},
        home=str(tmp_path / "home"),
    )

    assert paths.data_root == tmp_path / "Local" / "FrameRelay"
    assert paths.config_path == paths.data_root / "steam-launch.json"
    assert paths.launcher_path == paths.data_root / "bin" / "frame-relay-steam-launch.cmd"


@pytest.mark.parametrize(
    ("system", "legacy_relative"),
    [
        ("Linux", Path("config") / "apollo-streaming-lab" / "steam-launch.json"),
        ("Windows", Path("Local") / "ApolloStreamingLab" / "steam-launch.json"),
    ],
)
def test_migrate_legacy_profile(tmp_path, system, legacy_relative):
    env = (
        {"LOCALAPPDATA": str(tmp_path / "Local")}
        if system == "Windows"
        else {"XDG_CONFIG_HOME": str(tmp_path / "config")}
    )
    paths = steamsetup.install_paths(
        system=system,
        env=env,
        home=str(tmp_path / "home"),
    )
    legacy = tmp_path / legacy_relative
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"hub_url": "http://hub", "client_role": "moonlight"}),
        encoding="utf-8",
    )

    assert steamsetup.migrate_legacy_profile(
        paths, system=system, env=env, home=str(tmp_path / "home")
    ) is True
    assert json.loads(paths.config_path.read_text(encoding="utf-8"))[
        "client_role"
    ] == "moonlight"
    assert legacy.is_file()


def test_choose_client_role_prompts_for_moonlight_or_artemis():
    answers = iter(["invalid", "artemis"])
    assert steamsetup.choose_client_role(
        None, interactive=True, input_func=lambda prompt: next(answers)
    ) == "artemis"


def test_choose_client_role_requires_flag_without_terminal():
    with pytest.raises(steamsetup.SetupError, match="--client-role"):
        steamsetup.choose_client_role(None, interactive=False)


def test_write_profile_preserves_existing_config(tmp_path):
    paths = steamsetup.install_paths(
        system="Linux",
        env={"XDG_CONFIG_HOME": str(tmp_path / "config")},
        home=str(tmp_path),
    )
    paths.config_path.parent.mkdir(parents=True)
    original = {
        "hub_url": "http://hub",
        "client_role": "moonlight",
        "comparison_label": "existing",
    }
    paths.config_path.write_text(json.dumps(original), encoding="utf-8")

    profile = steamsetup.write_profile(
        paths,
        role=None,
        hub_url=None,
        reconfigure=False,
        interactive=False,
    )

    assert profile.client_role == "moonlight"
    assert json.loads(paths.config_path.read_text(encoding="utf-8")) == original


def test_write_profile_reconfigure_changes_selected_role(tmp_path):
    paths = steamsetup.install_paths(
        system="Linux",
        env={"XDG_CONFIG_HOME": str(tmp_path / "config")},
        home=str(tmp_path),
    )
    paths.config_path.parent.mkdir(parents=True)
    paths.config_path.write_text(
        json.dumps(
            {
                "hub_url": "http://old-hub",
                "client_role": "moonlight",
                "comparison_label": "keep-me",
            }
        ),
        encoding="utf-8",
    )

    profile = steamsetup.write_profile(
        paths,
        role="artemis",
        hub_url="http://new-hub",
        reconfigure=True,
        interactive=False,
    )

    stored = json.loads(paths.config_path.read_text(encoding="utf-8"))
    assert profile.client_role == "artemis"
    assert stored["comparison_label"] == "keep-me"


def test_parse_shortcuts_vdf_reads_signed_appid(tmp_path):
    config_dir = tmp_path / "userdata" / "1" / "config"
    shortcuts = steamsetup.parse_shortcuts_vdf(
        _shortcuts_vdf(
            [
                (
                    -1441195210,
                    "Moonlight",
                    '"/usr/bin/flatpak"',
                    "run com.moonlight_stream.Moonlight",
                )
            ]
        ),
        config_dir,
    )

    assert len(shortcuts) == 1
    assert shortcuts[0].appname == "Moonlight"
    assert shortcuts[0].grid_id == 2853772086
    assert shortcuts[0].config_dir == config_dir
    assert shortcuts[0].launch_options == "run com.moonlight_stream.Moonlight"


def test_parse_shortcuts_vdf_rejects_malformed_data(tmp_path):
    with pytest.raises(steamsetup.VdfError):
        steamsetup.parse_shortcuts_vdf(b"\x00broken", tmp_path)


def test_select_shortcut_uses_role_or_explicit_filter(tmp_path):
    shortcuts = [
        steamsetup.SteamShortcut(1, "Moonlight", "moonlight.exe", "", tmp_path),
        steamsetup.SteamShortcut(
            2, "Artemis Preview", "artemis.exe", "", tmp_path
        ),
    ]

    assert steamsetup.select_shortcut(
        shortcuts, "moonlight", interactive=False
    ).appid == 1
    assert steamsetup.select_shortcut(
        shortcuts,
        "moonlight",
        shortcut_filter="preview",
        interactive=False,
    ).appid == 2


def test_install_artwork_uses_same_sources_and_steam_names(tmp_path):
    paths = steamsetup.InstallPaths(
        system="Linux",
        data_root=tmp_path / "install",
        config_path=tmp_path / "config.json",
        state_root=tmp_path / "state",
        launcher_path=tmp_path / "bin" / "launcher",
    )
    paths.artwork_root.mkdir(parents=True)
    for name in steamsetup.ARTWORK_FILES:
        (paths.artwork_root / name).write_bytes(name.encode())
    config_dir = tmp_path / "steam" / "userdata" / "1" / "config"
    shortcut = steamsetup.SteamShortcut(
        -1, "Artemis", "artemis.exe", "", config_dir
    )

    installed = steamsetup.install_artwork(paths, shortcut)

    assert {path.name for path in installed} == {
        "4294967295p.png",
        "4294967295.png",
        "4294967295_hero.png",
        "4294967295_logo.png",
    }
    assert (config_dir / "grid" / "4294967295p.png").read_bytes() == b"portrait-grid.png"


@pytest.mark.parametrize("system", ["Linux", "Windows"])
def test_run_installs_payload_profile_and_launcher_without_artwork(tmp_path, system):
    env = (
        {"LOCALAPPDATA": str(tmp_path / "Local")}
        if system == "Windows"
        else {
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_BIN_HOME": str(tmp_path / "bin"),
        }
    )
    config_dir = tmp_path / "steam" / "userdata" / "1" / "config"
    config_dir.mkdir(parents=True)
    config_dir.joinpath("shortcuts.vdf").write_bytes(
        _shortcuts_vdf(
            [
                (
                    1,
                    "Moonlight",
                    '"client"',
                    "run com.moonlight_stream.Moonlight",
                )
            ]
        )
    )
    args = steamsetup.build_parser().parse_args(
        [
            "--client-role",
            "moonlight",
            "--hub-url",
            "http://hub:8080",
            "--skip-artwork",
            "--steam-config-dir",
            str(config_dir),
        ]
    )

    paths = steamsetup.run(
        args,
        system=system,
        env=env,
        home=str(tmp_path / "home"),
        repo_root=ROOT,
        interactive=False,
    )

    assert paths.launcher_path.is_file()
    assert steamsetup.legacy_launcher_path(paths).is_file()
    assert (paths.lib_root / "frame_relay_collector" / "steamlaunch.py").is_file()
    assert (paths.artwork_root / "portrait-grid.png").is_file()
    stored = json.loads(paths.config_path.read_text(encoding="utf-8"))
    assert stored["client_role"] == "moonlight"
    assert stored["hub_url"] == "http://hub:8080"
    assert not (config_dir / "grid").exists()


def test_run_applies_shared_artwork_to_selected_shortcut(tmp_path):
    config_dir = tmp_path / "steam" / "userdata" / "1" / "config"
    config_dir.mkdir(parents=True)
    config_dir.joinpath("shortcuts.vdf").write_bytes(
        _shortcuts_vdf([(-1, "Artemis", '"C:\\Apps\\Artemis.exe"', "")])
    )
    env = {
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }
    args = steamsetup.build_parser().parse_args(
        [
            "--client-role",
            "artemis",
            "--hub-url",
            "http://hub:8080",
            "--steam-config-dir",
            str(config_dir),
        ]
    )

    paths = steamsetup.run(
        args,
        system="Windows",
        env=env,
        home=str(tmp_path / "home"),
        repo_root=ROOT,
        interactive=False,
    )

    grid = config_dir / "grid"
    assert (grid / "4294967295p.png").read_bytes() == (
        paths.artwork_root / "portrait-grid.png"
    ).read_bytes()
    assert (grid / "4294967295.png").is_file()
    assert (grid / "4294967295_hero.png").is_file()
    assert (grid / "4294967295_logo.png").is_file()


def test_launch_options_preserve_flatpak_arguments(tmp_path):
    paths = steamsetup.InstallPaths(
        system="Linux",
        data_root=tmp_path,
        config_path=tmp_path / "config.json",
        state_root=tmp_path / "state",
        launcher_path=tmp_path / "bin" / "frame-relay-steam-launch",
    )
    shortcut = steamsetup.SteamShortcut(
        1,
        "Moonlight",
        '"/usr/bin/flatpak"',
        "run --branch=stable com.moonlight_stream.Moonlight",
        tmp_path,
    )

    assert steamsetup.launch_options(paths, shortcut) == (
        f'"{paths.launcher_path}" -- %command% '
        "run --branch=stable com.moonlight_stream.Moonlight"
    )


def test_launch_options_preserve_existing_command_wrapper(tmp_path):
    paths = steamsetup.InstallPaths(
        system="Windows",
        data_root=tmp_path,
        config_path=tmp_path / "config.json",
        state_root=tmp_path / "state",
        launcher_path=tmp_path / "frame-relay-steam-launch.cmd",
    )
    shortcut = steamsetup.SteamShortcut(
        1,
        "Artemis",
        '"C:\\Apps\\Artemis.exe"',
        "gamemoderun %command% --fullscreen",
        tmp_path,
    )

    assert steamsetup.launch_options(paths, shortcut) == (
        f'"{paths.launcher_path}" -- gamemoderun %command% --fullscreen'
    )


def test_launch_options_keep_linux_environment_assignments_outside_wrapper(tmp_path):
    paths = steamsetup.InstallPaths(
        system="Linux",
        data_root=tmp_path,
        config_path=tmp_path / "config.json",
        state_root=tmp_path / "state",
        launcher_path=tmp_path / "frame-relay-steam-launch",
    )
    shortcut = steamsetup.SteamShortcut(
        1,
        "Moonlight",
        '"/usr/bin/flatpak"',
        'MANGOHUD=1 PROFILE="couch test" gamemoderun %command% --fullscreen',
        tmp_path,
    )

    assert steamsetup.launch_options(paths, shortcut) == (
        'MANGOHUD=1 PROFILE="couch test" '
        f'"{paths.launcher_path}" -- gamemoderun %command% --fullscreen'
    )
