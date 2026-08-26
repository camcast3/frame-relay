"""User-local Steam wrapper installation for Windows and Linux."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import struct
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import steamlaunch

ARTWORK_FILES = {
    "portrait-grid.png": "{grid_id}p.png",
    "wide-grid.png": "{grid_id}.png",
    "hero-background.png": "{grid_id}_hero.png",
    "logo.png": "{grid_id}_logo.png",
}
ENV_ASSIGNMENT = re.compile(
    r"""(?x)
    (?P<assignment>
        [A-Za-z_][A-Za-z0-9_]*=
        (?:
            "(?:[^"\\]|\\.)*"
            |
            '[^']*'
            |
            [^\s]+
        )
    )
    \s+
    """
)


class SetupError(RuntimeError):
    """Steam wrapper setup cannot continue safely."""


class VdfError(ValueError):
    """A Steam shortcuts.vdf file could not be parsed."""


@dataclass(frozen=True)
class InstallPaths:
    system: str
    data_root: Path
    config_path: Path
    state_root: Path
    launcher_path: Path

    @property
    def lib_root(self) -> Path:
        return self.data_root / "lib"

    @property
    def artwork_root(self) -> Path:
        return self.data_root / "artwork"


@dataclass(frozen=True)
class SteamShortcut:
    appid: int
    appname: str
    exe: str
    launch_options: str
    config_dir: Path

    @property
    def grid_id(self) -> int:
        return self.appid & 0xFFFFFFFF


def install_paths(
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: str | None = None,
) -> InstallPaths:
    system = system or platform.system()
    env = os.environ if env is None else env
    home_path = Path(home if home is not None else Path.home())
    config_path = steamlaunch.default_config_path(system=system, env=env, home=str(home_path))
    if system == "Windows":
        root = Path(env.get("LOCALAPPDATA") or home_path / "AppData" / "Local")
        data_root = root / "ApolloStreamingLab"
        return InstallPaths(
            system=system,
            data_root=data_root,
            config_path=config_path,
            state_root=data_root / "logs",
            launcher_path=data_root / "bin" / "asl-steam-launch.cmd",
        )
    data_root = (
        Path(env["XDG_DATA_HOME"]) / "apollo-streaming-lab"
        if env.get("XDG_DATA_HOME")
        else home_path / ".local" / "share" / "apollo-streaming-lab"
    )
    state_root = (
        Path(env["XDG_STATE_HOME"]) / "apollo-streaming-lab"
        if env.get("XDG_STATE_HOME")
        else home_path / ".local" / "state" / "apollo-streaming-lab"
    )
    bin_root = Path(env.get("XDG_BIN_HOME") or home_path / ".local" / "bin")
    return InstallPaths(
        system=system,
        data_root=data_root,
        config_path=config_path,
        state_root=state_root,
        launcher_path=bin_root / "asl-steam-launch",
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _copy_directory_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / f".{target.name}.stage-{uuid.uuid4().hex}"
    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    shutil.copytree(
        source,
        stage,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    moved_existing = False
    try:
        if target.exists():
            target.replace(backup)
            moved_existing = True
        stage.replace(target)
    except BaseException:
        if not target.exists() and moved_existing and backup.exists():
            backup.replace(target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if backup.exists():
            shutil.rmtree(backup)


def _copy_file_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_name(f".{target.name}.stage-{uuid.uuid4().hex}")
    shutil.copy2(source, stage)
    os.replace(stage, target)


def install_payload(paths: InstallPaths, *, repo_root: Path | None = None) -> None:
    root = repo_root or _repo_root()
    package_source = root / "collectors" / "asl_collector"
    artwork_source = root / "assets" / "steam" / "streaming-client"
    if not package_source.is_dir():
        raise SetupError(f"collector package not found: {package_source}")
    missing_art = sorted(name for name in ARTWORK_FILES if not (artwork_source / name).is_file())
    if missing_art:
        raise SetupError(f"Steam artwork is incomplete: {', '.join(missing_art)}")

    launcher_source = (
        root / "collectors" / "windows" / "asl-steam-launch.cmd"
        if paths.system == "Windows"
        else root / "collectors" / "linux" / "asl-steam-launch.sh"
    )
    if not launcher_source.is_file():
        raise SetupError(f"Steam launcher not found: {launcher_source}")

    _copy_directory_atomic(package_source, paths.lib_root / "asl_collector")
    _copy_directory_atomic(artwork_source, paths.artwork_root)
    _copy_file_atomic(launcher_source, paths.launcher_path)
    if paths.system != "Windows":
        paths.launcher_path.chmod(paths.launcher_path.stat().st_mode | 0o111)
    paths.state_root.mkdir(parents=True, exist_ok=True)


def _prompt_choice(
    prompt: str,
    choices: Sequence[str],
    *,
    input_func: Callable[[str], str] = input,
) -> str:
    display = "/".join(choice.capitalize() for choice in choices)
    while True:
        value = input_func(f"{prompt} [{display}]: ").strip().lower()
        if value in choices:
            return value
        print(f"Enter one of: {', '.join(choices)}")


def choose_client_role(
    role: str | None,
    *,
    interactive: bool,
    input_func: Callable[[str], str] = input,
) -> str:
    if role:
        normalized = role.strip().lower()
        if normalized not in steamlaunch.CLIENT_ROLES:
            raise SetupError("client role must be moonlight or artemis")
        return normalized
    if not interactive:
        raise SetupError(
            "client role is required without a terminal; pass --client-role moonlight|artemis"
        )
    return _prompt_choice(
        "Which Steam client shortcut are you configuring?",
        ("moonlight", "artemis"),
        input_func=input_func,
    )


def choose_hub_url(
    hub_url: str | None,
    *,
    interactive: bool,
    input_func: Callable[[str], str] = input,
) -> str:
    if hub_url:
        value = hub_url.strip()
    elif interactive:
        value = input_func("Apollo Streaming Lab hub URL: ").strip()
    else:
        raise SetupError("hub URL is required without a terminal; pass --hub-url")
    try:
        return steamlaunch.parse_profile(
            {"hub_url": value, "client_role": "moonlight"}
        ).hub_url
    except steamlaunch.ProfileError as exc:
        raise SetupError(str(exc)) from exc


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise SetupError(
            f"invalid existing profile {path}: line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise SetupError(f"cannot read existing profile {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupError(f"existing profile must contain a JSON object: {path}")
    return data


def write_profile(
    paths: InstallPaths,
    *,
    role: str | None,
    hub_url: str | None,
    reconfigure: bool,
    interactive: bool,
    input_func: Callable[[str], str] = input,
) -> steamlaunch.SteamProfile:
    existing = _read_json_object(paths.config_path)
    if existing and not reconfigure:
        try:
            profile = steamlaunch.parse_profile(existing)
        except steamlaunch.ProfileError as exc:
            raise SetupError(f"invalid existing profile {paths.config_path}: {exc}") from exc
        if role and profile.client_role != role.lower():
            raise SetupError(
                f"profile already selects {profile.client_role}; use --reconfigure to change it"
            )
        if hub_url and profile.hub_url != hub_url.rstrip("/"):
            raise SetupError("profile already has a different hub URL; use --reconfigure")
        print(f"preserving existing profile: {paths.config_path}")
        return profile

    selected_role = choose_client_role(role, interactive=interactive, input_func=input_func)
    selected_hub = choose_hub_url(hub_url, interactive=interactive, input_func=input_func)
    data = existing if reconfigure else {}
    data["hub_url"] = selected_hub
    data["client_role"] = selected_role
    data.setdefault("name_template", steamlaunch.DEFAULT_NAME_TEMPLATE)
    data.setdefault(
        "collector",
        {
            "interval": steamlaunch.DEFAULT_INTERVAL,
            "post_interval": steamlaunch.DEFAULT_POST_INTERVAL,
            "screenshot_poll_interval": steamlaunch.DEFAULT_SCREENSHOT_POLL_INTERVAL,
        },
    )
    try:
        profile = steamlaunch.parse_profile(data)
    except steamlaunch.ProfileError as exc:
        raise SetupError(f"profile settings are invalid: {exc}") from exc

    paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    stage = paths.config_path.with_name(
        f".{paths.config_path.name}.stage-{uuid.uuid4().hex}"
    )
    stage.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(stage, paths.config_path)
    print(f"wrote profile: {paths.config_path}")
    return profile


def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        raise VdfError("unterminated string")
    return data[offset:end].decode("utf-8", errors="replace"), end + 1


def _parse_vdf_object(data: bytes, offset: int) -> tuple[dict[str, Any], int]:
    values: dict[str, Any] = {}
    while offset < len(data):
        value_type = data[offset]
        offset += 1
        if value_type == 0x08:
            return values, offset
        key, offset = _read_cstring(data, offset)
        if value_type == 0x00:
            value, offset = _parse_vdf_object(data, offset)
        elif value_type == 0x01:
            value, offset = _read_cstring(data, offset)
        elif value_type == 0x02:
            if offset + 4 > len(data):
                raise VdfError("truncated int32 value")
            value = struct.unpack_from("<i", data, offset)[0]
            offset += 4
        elif value_type == 0x07:
            if offset + 8 > len(data):
                raise VdfError("truncated uint64 value")
            value = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
        else:
            raise VdfError(f"unsupported binary VDF value type 0x{value_type:02x}")
        values[key] = value
    raise VdfError("object is missing its end marker")


def parse_shortcuts_vdf(data: bytes, config_dir: Path) -> list[SteamShortcut]:
    try:
        root, offset = _parse_vdf_object(data, 0)
    except (IndexError, UnicodeError, struct.error) as exc:
        raise VdfError(f"malformed binary VDF: {exc}") from exc
    if offset != len(data):
        raise VdfError("unexpected bytes after the root object")
    shortcuts = root.get("shortcuts")
    if not isinstance(shortcuts, dict):
        raise VdfError("binary VDF does not contain a shortcuts object")

    out: list[SteamShortcut] = []
    for entry in shortcuts.values():
        if not isinstance(entry, dict):
            continue
        normalized = {str(key).lower(): value for key, value in entry.items()}
        appid = normalized.get("appid")
        appname = normalized.get("appname")
        exe = normalized.get("exe")
        launch_options = normalized.get("launchoptions", "")
        if isinstance(appid, int) and isinstance(appname, str) and isinstance(exe, str):
            out.append(
                SteamShortcut(
                    appid=appid,
                    appname=appname,
                    exe=exe,
                    launch_options=(
                        launch_options if isinstance(launch_options, str) else ""
                    ),
                    config_dir=config_dir,
                )
            )
    return out


def _windows_steam_roots(env: Mapping[str, str]) -> list[Path]:
    roots: list[Path] = []
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        if env.get(key):
            roots.append(Path(env[key]) / "Steam")
    try:
        import winreg

        for hive, subkey in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "SteamPath")
                    roots.append(Path(value))
            except OSError:
                continue
    except ImportError:
        pass
    return roots


def candidate_steam_config_dirs(
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: str | None = None,
    explicit: Sequence[str | os.PathLike[str]] = (),
) -> list[Path]:
    system = system or platform.system()
    env = os.environ if env is None else env
    home_path = Path(home if home is not None else Path.home())
    configs: list[Path] = []
    for value in explicit:
        path = Path(value)
        configs.append(path if path.name == "config" else path / "config")

    roots = (
        _windows_steam_roots(env)
        if system == "Windows"
        else [
            home_path / ".local" / "share" / "Steam",
            home_path / ".steam" / "steam",
            home_path
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".local"
            / "share"
            / "Steam",
        ]
    )
    for root in roots:
        userdata = root / "userdata"
        if userdata.is_dir():
            configs.extend(path / "config" for path in userdata.iterdir() if path.is_dir())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in configs:
        key = os.path.normcase(str(path.resolve()))
        if key not in seen and (path / "shortcuts.vdf").is_file():
            seen.add(key)
            unique.append(path)
    return unique


def read_steam_shortcuts(config_dirs: Sequence[Path]) -> list[SteamShortcut]:
    shortcuts: list[SteamShortcut] = []
    for config_dir in config_dirs:
        path = config_dir / "shortcuts.vdf"
        try:
            shortcuts.extend(parse_shortcuts_vdf(path.read_bytes(), config_dir))
        except OSError as exc:
            raise SetupError(f"cannot read {path}: {exc}") from exc
        except VdfError as exc:
            raise SetupError(f"cannot parse {path}: {exc}") from exc
    return shortcuts


def select_shortcut(
    shortcuts: Sequence[SteamShortcut],
    role: str,
    *,
    shortcut_filter: str | None = None,
    interactive: bool,
    input_func: Callable[[str], str] = input,
) -> SteamShortcut:
    needle = (shortcut_filter or role).lower()
    matches = [
        shortcut
        for shortcut in shortcuts
        if needle in shortcut.appname.lower() or needle in shortcut.exe.lower()
    ]
    if not matches:
        raise SetupError(
            f"no Steam shortcut matched {needle!r}; add the client to Steam first or "
            "pass --shortcut with part of its name/path"
        )
    if len(matches) == 1:
        return matches[0]
    if not interactive:
        names = ", ".join(shortcut.appname for shortcut in matches)
        raise SetupError(f"multiple Steam shortcuts matched {needle!r}: {names}")

    print("Matching Steam shortcuts:")
    for index, shortcut in enumerate(matches, 1):
        print(f"  [{index}] {shortcut.appname} - {shortcut.exe}")
    while True:
        value = input_func(f"Select 1-{len(matches)}: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(matches):
            return matches[int(value) - 1]
        print("Enter a valid shortcut number")


def install_artwork(paths: InstallPaths, shortcut: SteamShortcut) -> list[Path]:
    grid_dir = shortcut.config_dir / "grid"
    grid_dir.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    for source_name, target_pattern in ARTWORK_FILES.items():
        source = paths.artwork_root / source_name
        target = grid_dir / target_pattern.format(grid_id=shortcut.grid_id)
        stem = target.stem
        for sibling in grid_dir.glob(stem + ".*"):
            if sibling != target and sibling.is_file():
                sibling.unlink()
        _copy_file_atomic(source, target)
        installed.append(target)
    return installed


def launch_options(paths: InstallPaths, shortcut: SteamShortcut | None = None) -> str:
    original = shortcut.launch_options.strip() if shortcut else ""
    env_assignments: list[str] = []
    command_text = original
    if paths.system != "Windows" and "%command%" in original.lower():
        offset = 0
        while True:
            match = ENV_ASSIGNMENT.match(original, offset)
            if not match:
                break
            env_assignments.append(match.group("assignment"))
            offset = match.end()
        command_text = original[offset:].strip()

    if "%command%" in command_text.lower():
        child_command = command_text
    else:
        child_command = "%command%"
        if command_text:
            child_command += " " + command_text
    prefix = " ".join(env_assignments)
    if prefix:
        prefix += " "
    return f'{prefix}"{paths.launcher_path}" -- {child_command}'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asl-steam-setup",
        description="Install the ASL Steam wrapper and shared client artwork",
    )
    parser.add_argument("--client-role", choices=sorted(steamlaunch.CLIENT_ROLES))
    parser.add_argument("--hub-url")
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--shortcut", help="substring matching the Steam shortcut name/path")
    parser.add_argument(
        "--steam-config-dir",
        action="append",
        default=[],
        help="Steam user config directory override (repeatable)",
    )
    parser.add_argument("--skip-artwork", action="store_true")
    return parser


def run(
    args: argparse.Namespace,
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: str | None = None,
    repo_root: Path | None = None,
    interactive: bool | None = None,
    input_func: Callable[[str], str] = input,
) -> InstallPaths:
    interactive = sys.stdin.isatty() if interactive is None else interactive
    paths = install_paths(system=system, env=env, home=home)
    profile = write_profile(
        paths,
        role=args.client_role,
        hub_url=args.hub_url,
        reconfigure=args.reconfigure,
        interactive=interactive,
        input_func=input_func,
    )
    install_payload(paths, repo_root=repo_root)

    config_dirs = candidate_steam_config_dirs(
        system=system,
        env=env,
        home=home,
        explicit=args.steam_config_dir,
    )
    if not config_dirs:
        raise SetupError(
            "no Steam user config with shortcuts.vdf was found; run Steam and add the "
            "client shortcut first"
        )
    shortcut = select_shortcut(
        read_steam_shortcuts(config_dirs),
        profile.client_role,
        shortcut_filter=args.shortcut,
        interactive=interactive,
        input_func=input_func,
    )
    if not args.skip_artwork:
        installed = install_artwork(paths, shortcut)
        print(
            f"installed shared artwork for {shortcut.appname} "
            f"(shortcut grid id {shortcut.grid_id}):"
        )
        for path in installed:
            print(f"  {path}")

    print(f"installed Steam launcher: {paths.launcher_path}")
    print("Set the shortcut's Steam Launch Options to:")
    print(f"  {launch_options(paths, shortcut)}")
    print("Restart Steam after changing Launch Options or artwork.")
    return paths


def main(argv: Sequence[str] | None = None) -> None:
    try:
        run(build_parser().parse_args(argv))
    except SetupError as exc:
        raise SystemExit(f"Steam wrapper setup failed: {exc}") from exc


if __name__ == "__main__":
    main()
