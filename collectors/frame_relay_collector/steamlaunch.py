"""Steam Game Mode / Big Picture launcher for tracked client sessions."""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import platform
import socket
import string
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from . import session

CLIENT_ROLES = {"moonlight", "artemis"}
NETWORK_PATHS = {
    "local-LAN",
    "remote-WireGuard",
    "remote-Tailscale",
    "remote-WAN",
}
TOP_LEVEL_FIELDS = {
    "hub_url",
    "client_role",
    "name_template",
    "comparison_label",
    "apollo_app",
    "game_title",
    "network_path",
    "client_platform",
    "requested_settings",
    "collector",
}
REQUESTED_FIELDS = {"codec", "resolution", "fps", "bitrate_mbps", "hdr"}
COLLECTOR_FIELDS = {"interval", "post_interval", "screenshot_poll_interval"}
DEFAULT_NAME_TEMPLATE = "{hostname} - {client_role} - {timestamp}"
DEFAULT_INTERVAL = 15.0
DEFAULT_POST_INTERVAL = 30.0
DEFAULT_SCREENSHOT_POLL_INTERVAL = 3.0
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024


class ProfileError(ValueError):
    """The Steam launch profile is missing or invalid."""


@dataclass(frozen=True)
class SteamProfile:
    hub_url: str
    client_role: str
    name_template: str = DEFAULT_NAME_TEMPLATE
    comparison_label: str | None = None
    apollo_app: str | None = None
    game_title: str | None = None
    network_path: str | None = None
    client_platform: str | None = None
    codec: str | None = None
    resolution: str | None = None
    fps: int | None = None
    bitrate_mbps: int | None = None
    hdr: bool | None = None
    interval: float = DEFAULT_INTERVAL
    post_interval: float = DEFAULT_POST_INTERVAL
    screenshot_poll_interval: float = DEFAULT_SCREENSHOT_POLL_INTERVAL


def default_config_path(
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: str | None = None,
) -> Path:
    """Return the platform-native user config path."""
    system = system or platform.system()
    env = os.environ if env is None else env
    home_path = Path(home if home is not None else Path.home())
    if system == "Windows":
        root = Path(env.get("LOCALAPPDATA") or home_path / "AppData" / "Local")
        return root / "FrameRelay" / "steam-launch.json"
    root = Path(env.get("XDG_CONFIG_HOME") or home_path / ".config")
    return root / "frame-relay" / "steam-launch.json"


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"{field} must be a JSON object")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProfileError(f"{field} contains unsupported field(s): {', '.join(unknown)}")


def _required_text(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(data: Mapping[str, Any], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{field} must be a non-empty string when provided")
    return value.strip()


def _optional_positive_int(data: Mapping[str, Any], field: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProfileError(f"{field} must be a positive integer when provided")
    return value


def _nonnegative_number(data: Mapping[str, Any], field: str, default: float) -> float:
    value = data.get(field, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ProfileError(f"{field} must be a non-negative number")
    return float(value)


def _positive_number(data: Mapping[str, Any], field: str, default: float) -> float:
    value = _nonnegative_number(data, field, default)
    if value == 0:
        raise ProfileError(f"{field} must be greater than zero")
    return value


def _validate_name_template(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileError("name_template must be a non-empty string")
    allowed = {"hostname", "client_role", "date", "time", "timestamp"}
    try:
        fields = list(string.Formatter().parse(value))
    except ValueError as exc:
        raise ProfileError(f"invalid name_template: {exc}") from exc
    for _, field_name, format_spec, conversion in fields:
        if field_name is None:
            continue
        if field_name not in allowed:
            raise ProfileError(f"unsupported name_template field: {field_name}")
        if format_spec or conversion:
            raise ProfileError("name_template fields do not support formats or conversions")
    return value.strip()


def parse_profile(data: object) -> SteamProfile:
    """Validate decoded JSON and return an immutable launch profile."""
    if not isinstance(data, dict):
        raise ProfileError("profile must be a JSON object")
    _reject_unknown(data, TOP_LEVEL_FIELDS, "profile")

    hub_url = _required_text(data, "hub_url").rstrip("/")
    parsed_url = urlparse(hub_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ProfileError("hub_url must be an absolute http:// or https:// URL")

    client_role = _required_text(data, "client_role").lower()
    if client_role not in CLIENT_ROLES:
        raise ProfileError("client_role must be moonlight or artemis")

    name_template = _validate_name_template(
        data.get("name_template", DEFAULT_NAME_TEMPLATE)
    )

    requested = _mapping(data.get("requested_settings"), "requested_settings")
    collector = _mapping(data.get("collector"), "collector")
    _reject_unknown(requested, REQUESTED_FIELDS, "requested_settings")
    _reject_unknown(collector, COLLECTOR_FIELDS, "collector")

    hdr = requested.get("hdr")
    if hdr is not None and not isinstance(hdr, bool):
        raise ProfileError("requested_settings.hdr must be true or false")

    network_path = _optional_text(data, "network_path")
    if network_path is not None and network_path not in NETWORK_PATHS:
        raise ProfileError(
            "network_path must be one of: " + ", ".join(sorted(NETWORK_PATHS))
        )

    return SteamProfile(
        hub_url=hub_url,
        client_role=client_role,
        name_template=name_template,
        comparison_label=_optional_text(data, "comparison_label"),
        apollo_app=_optional_text(data, "apollo_app"),
        game_title=_optional_text(data, "game_title"),
        network_path=network_path,
        client_platform=_optional_text(data, "client_platform"),
        codec=_optional_text(requested, "codec"),
        resolution=_optional_text(requested, "resolution"),
        fps=_optional_positive_int(requested, "fps"),
        bitrate_mbps=_optional_positive_int(requested, "bitrate_mbps"),
        hdr=hdr,
        interval=_nonnegative_number(collector, "interval", DEFAULT_INTERVAL),
        post_interval=_nonnegative_number(
            collector, "post_interval", DEFAULT_POST_INTERVAL
        ),
        screenshot_poll_interval=_positive_number(
            collector,
            "screenshot_poll_interval",
            DEFAULT_SCREENSHOT_POLL_INTERVAL,
        ),
    )


def load_profile(path: str | os.PathLike[str]) -> SteamProfile:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise ProfileError(f"Steam launch profile not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(
            f"invalid JSON in Steam launch profile {config_path}: "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise ProfileError(f"cannot read Steam launch profile {config_path}: {exc}") from exc
    return parse_profile(data)


def render_session_name(
    profile: SteamProfile,
    *,
    now: datetime | None = None,
    hostname: str | None = None,
) -> str:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    values = {
        "hostname": hostname or socket.gethostname(),
        "client_role": profile.client_role,
        "date": current.strftime("%Y-%m-%d"),
        "time": current.strftime("%H%M%S"),
        "timestamp": current.strftime("%Y%m%dT%H%M%S"),
    }
    try:
        rendered = profile.name_template.format_map(values).strip()
    except KeyError as exc:
        raise ProfileError(f"unsupported name_template field: {exc.args[0]}") from exc
    except ValueError as exc:
        raise ProfileError(f"invalid name_template: {exc}") from exc
    if not rendered:
        raise ProfileError("name_template rendered an empty session name")
    return rendered


def collector_argv(
    profile: SteamProfile,
    command: Sequence[str],
    *,
    now: datetime | None = None,
    hostname: str | None = None,
) -> list[str]:
    """Translate a profile and Steam's expanded command into collector CLI arguments."""
    if not command or not command[0]:
        raise ProfileError("Steam did not provide a client command after --")

    argv = [
        "--hub-url",
        profile.hub_url,
        "--source",
        "client",
        "--role",
        profile.client_role,
        "--create",
        "--stop-session",
        "--name",
        render_session_name(profile, now=now, hostname=hostname),
        "--launch",
        str(command[0]),
        "--interval",
        str(profile.interval),
        "--post-interval",
        str(profile.post_interval),
        "--screenshot-poll-interval",
        str(profile.screenshot_poll_interval),
    ]
    for argument in command[1:]:
        argv.append(f"--launch-arg={argument}")

    optional_values = [
        ("--comparison-label", profile.comparison_label),
        ("--apollo-app", profile.apollo_app),
        ("--game-title", profile.game_title),
        ("--network-path", profile.network_path),
        ("--client-platform", profile.client_platform),
        ("--codec", profile.codec),
        ("--resolution", profile.resolution),
        ("--fps", profile.fps),
        ("--bitrate-mbps", profile.bitrate_mbps),
    ]
    for flag, value in optional_values:
        if value is not None:
            argv.extend([flag, str(value)])
    if profile.hdr:
        argv.append("--hdr")
    elif profile.hdr is False:
        argv.append("--no-hdr")
    return argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frame-relay-steam-launch",
        description="Launch Moonlight or Artemis from Steam as a tracked Frame Relay session",
    )
    parser.add_argument("--config", help="Steam launch profile path")
    parser.add_argument("--log-file", help="append launcher output to this local file")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="client command supplied by Steam after --",
    )
    return parser


def _run(args: argparse.Namespace) -> None:
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    profile_path = Path(args.config) if args.config else default_config_path()
    try:
        profile = load_profile(profile_path)
        collector_args = collector_argv(profile, command)
    except ProfileError as exc:
        raise SystemExit(f"Steam launcher configuration error: {exc}") from exc
    session.main(collector_args)


def _rotate_log(path: Path, max_bytes: int = DEFAULT_LOG_MAX_BYTES) -> None:
    try:
        if path.stat().st_size < max_bytes:
            return
    except FileNotFoundError:
        return
    backup = path.with_name(path.name + ".1")
    try:
        backup.unlink()
    except FileNotFoundError:
        pass
    path.replace(backup)


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.log_file:
        _run(args)
        return

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log(log_path)
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            print(f"\n[{datetime.now().astimezone().isoformat()}] Steam launch started")
            try:
                _run(args)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    print(f"Steam launch failed: {exc}", file=sys.stderr)
                raise
            except BaseException:  # noqa: BLE001 - persist unexpected headless launcher failures
                traceback.print_exc()
                raise


if __name__ == "__main__":
    main()
