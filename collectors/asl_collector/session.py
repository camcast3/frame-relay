"""Session capture orchestrator + CLI.

Typical use on a machine under test (run with the system Python; stdlib only):

    # Apollo host
    python -m asl_collector --hub-url https://apollo-streaming-lab.<tailnet>.ts.net \
        --session-id 20260723T101951-ab12 --source host --role apollo \
        --log "C:\\Program Files\\Apollo\\config\\sunshine.log" --interval 15

    # Moonlight client (Linux); attach to the session the host just created (no id copy-paste)
    python3 -m asl_collector --hub-url https://apollo-streaming-lab.<tailnet>.ts.net \
        --attach-latest --source client --role moonlight \
        --log ~/.config/Moonlight*/Moonlight.log --interval 15 --duration 0

    # Artemis client (Windows); LIVE logs by launching the app and capturing its stderr
    python -m asl_collector --hub-url http://192.168.69.159:8080 --attach-latest \
        --source client --role artemis \
        --launch "C:\\Program Files\\Artemis Game Streaming\\Artemis.exe"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from . import (
    __version__,
    appfind,
    client,
    clientmeta,
    conninfo,
    displayprobe,
    hostmeta,
    logslice,
    logfind,
    screenshot,
)
from .netmon import LinkMonitor


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reader(stream, buf: list[str], lock: threading.Lock) -> None:
    """Drain a launched app's stdout/stderr line-by-line into a shared buffer (live)."""
    try:
        for line in iter(stream.readline, ""):
            with lock:
                buf.append(line)
    except Exception:  # noqa: BLE001 - stream closed / process gone
        pass


def _expand(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths or []:
        matches = glob.glob(p)
        out.extend(matches or [p])
    return out


def _platform_name() -> str:
    system = (platform.system() or "").strip()
    return "macOS" if system == "Darwin" else (system or sys.platform)


def _log_meta(role: str, capture_method: str, capture_path: str) -> dict[str, str]:
    return {
        "platform": _platform_name(),
        "role": role,
        "collector_version": __version__,
        "capture_method": capture_method,
        "capture_path": capture_path,
    }


def _display_payload_marker(samples: list[dict[str, Any]]) -> str:
    return json.dumps(
        [{k: v for k, v in sample.items() if k != "sampled_at"} for sample in samples],
        sort_keys=True,
    )


def _display_summary(samples: list[dict[str, Any]]) -> str:
    primary = next((s for s in samples if s.get("primary")), None)
    primary_name = None
    if primary:
        primary_name = primary.get("friendly_name") or primary.get("source_name")
    bits = [f"{len(samples)} path(s)"]
    virtual = sum(1 for s in samples if s.get("is_virtual") is True)
    hdr_enabled = sum(1 for s in samples if s.get("hdr_enabled") is True)
    if virtual:
        bits.append(f"{virtual} virtual")
    if hdr_enabled:
        bits.append(f"{hdr_enabled} HDR-on")
    if primary_name:
        bits.append(f"primary={primary_name}")
    return ", ".join(bits)


def _build_observations(source: str, role: str, log_text: str,
                        args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {}
    if log_text.strip():
        if source == "host":
            parsed = hostmeta.parse_apollo_metadata(log_text)
        else:
            parsed = clientmeta.parse_client_metadata(log_text, role)
        for field in ("apollo_app", "game_title", "client_version"):
            value = parsed.get(field)
            if value not in (None, ""):
                payload[field] = value
        requested = parsed.get("requested_settings")
        if isinstance(requested, dict) and requested:
            payload["requested_settings"] = dict(requested)
        hdr_details = parsed.get("hdr_details")
        if isinstance(hdr_details, dict) and hdr_details:
            payload["hdr_details"] = dict(hdr_details)
    if source == "client" and role in ("moonlight", "artemis"):
        payload["client_role"] = role
        payload.setdefault("client_platform", _platform_name())
    for field in ("comparison_label", "apollo_app", "game_title",
                  "client_platform", "client_version"):
        value = getattr(args, field, None)
        if value not in (None, ""):
            payload[field] = value
    return payload


def _enrich_host(hub: str, sid: str, log_text: str, client_ip: Optional[str],
                 args: argparse.Namespace) -> None:
    """Fill blank session metadata from the Apollo log + the live client connection.

    Log-derived: codec/resolution/fps/bitrate/hdr. Connection-derived: client (IP) and
    network_path (LAN / Tailscale / WAN). Only fills blanks - never overrides a value passed on
    the CLI or already set on the session (e.g. entered in the UI).
    """
    derived = hostmeta.parse_apollo_metadata(log_text) if log_text.strip() else {}
    net_path = conninfo.classify_network_path(client_ip, args.wg_subnet) if client_ip else None
    current = client.get_session(hub, sid) or {}
    patch: dict[str, object] = {}
    for field in ("codec", "resolution", "fps", "bitrate_mbps"):
        if derived.get(field) is not None and not current.get(field):
            patch[field] = derived[field]
    if derived.get("hdr") and not current.get("hdr"):
        patch["hdr"] = True
    if client_ip and args.client is None and not current.get("client"):
        patch["client"] = client_ip
    if net_path and args.network_path is None and not current.get("network_path"):
        patch["network_path"] = net_path
    if patch:
        client.patch_session(hub, sid, patch)
        print(f"auto-filled: {patch}")


DEFAULT_WG_SUBNETS = ["192.168.2.0/24"]  # user's WireGuard VLAN (override with --wg-subnet)

# How many times to retry one session in --watch mode before ignoring it. A session that
# cannot be captured stays on the awaiting-host list, so an unguarded retry loop would spin
# on it forever and never pick up the next test.
WATCH_MAX_FAILURES = 3
DEFAULT_SCREENSHOT_POLL_INTERVAL = 3.0


def _describe(s: dict) -> str:
    name = s.get("name") or "(unnamed)"
    host = s.get("host") or "?"
    created = (s.get("created_at") or "")[:19]
    return f"{name}  host={host}  {created}  ({s['id']})"


def _select_session(hub: str, attach_latest: bool = False) -> str:
    """Pick a session that has no client attached yet, without copy-pasting an id.

    The host creates the session; the client attaches to it from the hub's awaiting-client
    list (newest first). Selection needs no manual id entry in the common cases:

    * ``attach_latest`` -> take the newest awaiting-client session, no prompt (fully scripted).
    * exactly one awaiting session -> auto-attach to it, no prompt.
    * several awaiting sessions on a TTY -> prompt to choose one.
    """
    sessions = client.list_sessions(hub, awaiting_client=True)
    if not sessions:
        raise SystemExit(
            "no sessions awaiting a client on the hub; create one on the host first "
            "(or pass --session-id / --create)"
        )
    if attach_latest:
        chosen = sessions[0]
        print(f"attaching to latest awaiting-client session: {_describe(chosen)}")
        return chosen["id"]
    if len(sessions) == 1:
        chosen = sessions[0]
        print(f"attaching to the only awaiting-client session: {_describe(chosen)}")
        return chosen["id"]
    print("Sessions awaiting a client:")
    for i, s in enumerate(sessions, 1):
        print(f"  [{i}] {_describe(s)}")
    if not sys.stdin.isatty():
        raise SystemExit(
            "multiple sessions awaiting a client and no TTY to choose; "
            "pass --attach-latest to take the newest, or --session-id to pick one"
        )
    while True:
        choice = input(f"Select 1-{len(sessions)} (q to quit): ").strip().lower()
        if choice in ("q", ""):
            raise SystemExit("no session selected")
        if choice.isdigit() and 1 <= int(choice) <= len(sessions):
            return sessions[int(choice) - 1]["id"]
        print("invalid selection")


def run(args: argparse.Namespace) -> str:
    hub = args.hub_url.rstrip("/")
    machine = args.machine or platform.node()
    role = args.role or ("apollo" if args.source == "host" else "moonlight")
    if not args.wg_subnet:
        args.wg_subnet = list(DEFAULT_WG_SUBNETS)

    # Resolve the app to wrap *before* touching the hub, so a missing install cannot leave an
    # orphan session behind.
    if not args.launch and getattr(args, "launch_client", False):
        found = appfind.discover(role)
        if not found:
            raise SystemExit(
                f"--launch-client: no {role} app found in the usual install locations; "
                f"pass --launch <path> instead"
            )
        args.launch = found
        print(f"auto-detected {role} app: {found}")

    if args.watch:
        return _watch(hub, args, machine, role)

    sid = args.session_id
    if not sid:
        if not args.create:
            sid = _select_session(hub, attach_latest=args.attach_latest)
        else:
            # Default host/client to this machine's name based on which side we're capturing.
            default_host = args.host or (machine if args.source == "host" else None)
            default_client = args.client or (machine if args.source == "client" else None)
            requested = {
                key: value for key, value in {
                    "codec": args.codec,
                    "resolution": args.resolution,
                    "fps": args.fps,
                    "bitrate_mbps": args.bitrate_mbps,
                    "hdr": bool(args.hdr),
                }.items()
                if value is not None
            }
            payload = {
                "name": args.name, "host": default_host, "client": default_client,
                "network_path": args.network_path,
                "comparison_label": args.comparison_label,
                "apollo_app": args.apollo_app,
                "game_title": args.game_title,
                "client_role": role if args.source == "client" else None,
                "client_platform": (
                    args.client_platform or _platform_name()
                    if args.source == "client" else args.client_platform
                ),
                "client_version": args.client_version,
                "requested_settings": requested,
            }
            sid = client.create_session(
                hub, {key: value for key, value in payload.items() if value is not None}
            )
            print(f"created session {sid}")
    return _capture(hub, sid, args, machine, role)


def _session_started_at(hub: str, sid: str) -> Optional[datetime]:
    """When the session began, so a watching collector can back-fill its log from there."""
    try:
        s = client.get_session(hub, sid)
    except Exception:  # noqa: BLE001
        return None
    if not s:
        return None
    raw = s.get("started_at") or s.get("created_at")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _session_ended(hub: str, sid: str) -> bool:
    """True once the hub says this session is stopped, or it has been deleted."""
    try:
        s = client.get_session(hub, sid)
    except Exception:  # noqa: BLE001 - a hub blip is not a reason to stop capturing
        return False
    if s is None:
        return True
    return str(s.get("status", "")).lower() == "stopped"


def _newer_session_waiting(hub: str, sid: str) -> bool:
    """True when a *different* session is now awaiting a host - i.e. the next test started."""
    try:
        waiting = client.list_sessions(hub, awaiting_host=True)
    except Exception:  # noqa: BLE001
        return False
    return any(s.get("id") != sid for s in waiting)


def _watch(hub: str, args: argparse.Namespace, machine: str, role: str) -> str:
    """Run as a long-lived collector that follows whatever session is current.

    The client (or the UI) creates the session; this side just notices and contributes its log
    and link samples. Idempotent by construction: a session drops off the awaiting-host list as
    soon as we post to it, so restarting this process never double-captures, and it is safe to
    leave running across many tests.
    """
    print(f"watching {hub} for sessions to capture ({args.source}/{role}) on {machine}; "
          f"polling every {args.watch_interval}s - Ctrl+C to stop")
    last = ""
    failures: dict[str, int] = {}
    skip: set[str] = set()
    while True:
        try:
            waiting = client.list_sessions(hub, awaiting_host=True)
        except Exception as e:  # noqa: BLE001
            _print_once(f"hub unreachable, retrying: {e}", last)
            last = f"hub unreachable, retrying: {e}"
            time.sleep(args.watch_interval)
            continue
        last = ""
        target = next((s for s in waiting if s.get("id") not in skip), None)
        if target is None:
            time.sleep(args.watch_interval)
            continue

        sid = target["id"]
        print(f"\nattaching to session {sid} ({target.get('name') or 'unnamed'})")
        try:
            _capture(hub, sid, args, machine, role, watch=True)
            failures.pop(sid, None)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 - never let one bad session kill the watcher
            # A session we cannot capture stays on the awaiting-host list, so without a guard
            # we would spin on it forever and never reach the next one.
            failures[sid] = failures.get(sid, 0) + 1
            print(f"capture for {sid} failed ({failures[sid]}/{WATCH_MAX_FAILURES}): {e}")
            if failures[sid] >= WATCH_MAX_FAILURES:
                skip.add(sid)
                print(f"giving up on {sid}; ignoring it and watching for others")
            time.sleep(args.watch_interval)
            continue
        print("watching for the next session...")


def _print_once(msg: str, previous: str) -> None:
    """Avoid spamming an unreachable-hub message every poll."""
    if msg != previous:
        print(msg)


def _cleanup_screenshot_file(path: str | None) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _report_screenshot_failure(
    hub: str,
    sid: str,
    request_id: int,
    source: str,
    machine: str,
    token: str,
    error: str,
) -> bool:
    try:
        client.fail_screenshot_request(
            hub,
            sid,
            request_id,
            source,
            error,
            machine=machine,
            token=token,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - keep the capture alive if reporting fails
        print(f"screenshot request {request_id} failure report failed: {exc}")
        return False


def _preferred_screenshot_display(source: str) -> str | None:
    if source != "host" or platform.system() != "Windows":
        return None
    try:
        displays = displayprobe.detect()
    except Exception as exc:  # noqa: BLE001 - screenshot falls back to Windows primary
        print(f"preferred screenshot display detection failed: {exc}")
        return None
    candidate = next((row for row in displays if row.get("is_virtual") is True), None)
    if candidate is None:
        candidate = next((row for row in displays if row.get("primary") is True), None)
    if candidate is None:
        return None
    value = candidate.get("source_name")
    return str(value) if value not in (None, "") else None


def _process_screenshot_request(
    hub: str,
    sid: str,
    request_id: int,
    source: str,
    machine: str,
    token: str,
) -> bool:
    captured: dict[str, Any] | None = None
    try:
        captured = screenshot.capture(_preferred_screenshot_display(source))
        client.complete_screenshot_request(
            hub,
            sid,
            request_id,
            source,
            str(captured["path"]),
            machine=machine,
            captured_at=str(captured.get("captured_at") or ""),
            display_name=str(captured.get("display_name") or ""),
            token=token,
        )
        print(
            f"completed screenshot request {request_id} "
            f"({captured['width']}x{captured['height']})"
        )
        return True
    except Exception as exc:  # noqa: BLE001 - report request failures back to the hub
        message = str(exc) or exc.__class__.__name__
        print(f"screenshot request {request_id} failed: {message}")
        return _report_screenshot_failure(
            hub, sid, request_id, source, machine, token, message
        )
    finally:
        path = None
        if captured:
            raw_path = captured.get("path")
            if raw_path not in (None, ""):
                path = str(raw_path)
        _cleanup_screenshot_file(path)


def _screenshot_worker_loop(
    hub: str,
    sid: str,
    source: str,
    machine: str,
    token: str,
    poll_interval: float,
    stop_evt: threading.Event,
) -> None:
    seen: set[int] = set()
    wait_timeout = poll_interval if poll_interval > 0 else 0.1
    while not stop_evt.is_set():
        try:
            pending = client.pending_screenshot_requests(hub, sid, source, token=token)
        except Exception as exc:  # noqa: BLE001 - polling is best-effort
            print(f"screenshot request poll failed: {exc}")
        else:
            for request in pending:
                request_id = request.get("id")
                if not isinstance(request_id, int) or request_id in seen:
                    continue
                if _process_screenshot_request(
                    hub, sid, request_id, source, machine, token
                ):
                    seen.add(request_id)
        if stop_evt.wait(wait_timeout):
            break


def _start_screenshot_worker(
    hub: str,
    sid: str,
    source: str,
    machine: str,
    token: str | None,
    poll_interval: float,
    stop_evt: threading.Event,
) -> threading.Thread | None:
    token = (token or "").strip()
    if not token:
        return None
    worker = threading.Thread(
        target=_screenshot_worker_loop,
        args=(hub, sid, source, machine, token, poll_interval, stop_evt),
        daemon=True,
    )
    worker.start()
    return worker


def _capture(hub: str, sid: str, args: argparse.Namespace, machine: str, role: str,
             watch: bool = False) -> str:
    # Launch mode: the collector wraps the client app (Artemis/Moonlight-Qt) - it spawns it and
    # captures its stderr live, because Qt writes diagnostics there in real time while the
    # %TEMP% file it also keeps is buffered and only flushes in bursts. Capture ends when the
    # app exits, so "close the game stream" is all the operator has to do.
    launched = None
    stderr_buf: Optional[list[str]] = None
    stderr_lock = threading.Lock()

    launch = args.launch
    if launch:
        cmd = [launch] + list(args.launch_arg or [])
        try:
            launched = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
            )
        except OSError as e:
            raise SystemExit(f"failed to launch {cmd!r}: {e}")
        stderr_buf = []
        threading.Thread(target=_reader, args=(launched.stdout, stderr_buf, stderr_lock),
                         daemon=True).start()
        print(f"launched {cmd[0]} (pid {launched.pid}); capturing its stderr live")

    if not args.log and not launched:
        detected = logfind.discover(args.source, role)
        if detected:
            args.log = detected
            print(f"auto-detected {role} log: {detected[0]}")
        else:
            print(f"no {role} log auto-detected for this platform; pass --log, --launch or "
                  f"--launch-client")

    logs = _expand(args.log)
    start = _now()
    posted_offsets = {path: logslice.file_offset(path) for path in logs}
    posted_any = {path: False for path in logs}
    observed_log_parts: list[str] = []
    posted_link_idx = 0
    observation_marker = ""
    flush_lock = threading.Lock()
    display_enabled = args.source == "host" and platform.system() == "Windows"
    pending_displays: list[dict[str, Any]] = []
    display_marker = ""

    def _queue_display_snapshot(phase: str) -> None:
        nonlocal display_marker
        if not display_enabled:
            return
        snapshots = displayprobe.detect()
        if not snapshots:
            return
        for sample in snapshots:
            sample["machine"] = machine
            sample["phase"] = phase
        marker = _display_payload_marker(snapshots)
        if marker == display_marker:
            return
        pending_displays.extend(snapshots)
        display_marker = marker
        print(f"queued display snapshot ({phase}): {_display_summary(snapshots)}")

    def _post_display_samples() -> None:
        if not pending_displays:
            return
        batch = list(pending_displays)
        added = client.post_displays(hub, sid, batch)
        del pending_displays[:len(batch)]
        phases = ",".join(dict.fromkeys(str(sample.get("phase") or "?") for sample in batch))
        print(f"posted {added} display samples ({phases}; {_display_summary(batch)})")

    if not watch:
        _queue_display_snapshot("before")

    if watch:
        # The session already existed before we noticed it, so back-fill the log from when it
        # started rather than from now - otherwise the connect/handshake lines are lost.
        started = _session_started_at(hub, sid)
        if started:
            start = started
            for path in logs:
                back = logslice.slice_file(path, started, _now())
                if back.strip():
                    client.post_log(hub, sid, args.source, role, back, machine,
                                    meta=_log_meta(role, "file", path))
                    posted_any[path] = True
                    observed_log_parts.append(back)
                    print(f"back-filled {len(back.splitlines())} log lines from {path}")

    monitor = None
    conn_monitor = None
    if args.interval > 0:
        monitor = LinkMonitor(source=args.source, machine=machine, interval=args.interval)
        monitor.start()
        if args.source == "host":
            conn_monitor = conninfo.ClientMonitor(conninfo.apollo_ports(args.apollo_port), args.interval)
            conn_monitor.start()

    def flush(final: bool = False) -> None:
        """Post any log bytes / stderr / link samples not sent yet. Safe to call repeatedly."""
        nonlocal observation_marker, posted_link_idx
        with flush_lock:
            for path in logs:
                text, new_off = logslice.read_new(path, posted_offsets.get(path, 0))
                posted_offsets[path] = new_off
                if not text.strip() and final and not posted_any[path]:
                    # Nothing appended during the window (e.g. a static/complete log): fall back
                    # to a wall-clock slice of timestamped lines.
                    text = logslice.slice_file(path, start, _now())
                    if not text.strip():
                        continue
                elif not text.strip():
                    continue
                client.post_log(hub, sid, args.source, role, text, machine,
                                meta=_log_meta(role, "file", path))
                posted_any[path] = True
                print(f"posted {len(text.splitlines())} log lines from {path}")
                observed_log_parts.append(text)
            if stderr_buf is not None:
                with stderr_lock:
                    pending_lines = stderr_buf[:]
                    del stderr_buf[:]
                if pending_lines:
                    text = "".join(pending_lines)
                    client.post_log(hub, sid, args.source, role, text, machine,
                                    meta=_log_meta(role, "launch-stderr", launch))
                    print(f"posted {len(pending_lines)} log lines from <{launch} stderr>")
                    observed_log_parts.append(text)
            if monitor:
                pending = monitor.samples[posted_link_idx:]
                if pending:
                    added = client.post_links(hub, sid, list(pending))
                    posted_link_idx += len(pending)
                    aps = {s.get("bssid") for s in pending if s.get("bssid")}
                    print(f"posted {added} link samples ({len(aps)} distinct AP(s))")
            if not final:
                _queue_display_snapshot("during")
            _post_display_samples()
            try:
                payload = _build_observations(args.source, role, "\n".join(observed_log_parts), args)
                marker = json.dumps(payload, sort_keys=True) if payload else ""
                if payload and (final or marker != observation_marker):
                    client.post_observations(hub, sid, payload)
                    observation_marker = marker
                    print(f"posted observations: {', '.join(sorted(payload))}")
            except Exception as e:  # noqa: BLE001 - observation posting is best-effort
                print(f"observation post failed: {e}")
            # Live-fill blank session metadata (client IP / path / codec…) during capture, not
            # just on stop. _enrich_host re-reads the session each call and only fills blanks.
            if args.source == "host" and conn_monitor is not None:
                try:
                    _enrich_host(hub, sid, "\n".join(observed_log_parts), conn_monitor.current(), args)
                except Exception:  # noqa: BLE001 - enrichment is best-effort
                    pass

    stop_evt = threading.Event()
    flusher = None
    screenshot_worker = _start_screenshot_worker(
        hub,
        sid,
        args.source,
        machine,
        getattr(args, "screenshot_token", ""),
        float(getattr(args, "screenshot_poll_interval", DEFAULT_SCREENSHOT_POLL_INTERVAL)),
        stop_evt,
    )
    if args.post_interval and args.post_interval > 0:
        def _flush_loop() -> None:
            while not stop_evt.wait(args.post_interval):
                try:
                    flush(final=False)
                except Exception as e:  # keep capturing even if the hub blips
                    print(f"live post failed (will retry): {e}")
        flusher = threading.Thread(target=_flush_loop, daemon=True)
        flusher.start()

    live = "live-posting every %ss" % args.post_interval if flusher else "posting on stop"
    print(f"capturing session {sid} ({args.source}/{role}) on {machine} - "
          f"{'sampling link every %ss' % args.interval if monitor else 'no link sampling'}; {live}")
    _queue_display_snapshot("during")
    _post_display_samples()
    try:
        if watch:
            print("capturing until the session is stopped on the hub, or the next one starts "
                  "(Ctrl+C to stop watching)...")
            while True:
                time.sleep(args.watch_interval)
                if _session_ended(hub, sid):
                    print("session stopped on the hub")
                    break
                if _newer_session_waiting(hub, sid):
                    print("a newer session is awaiting a host; moving to it")
                    break
        elif args.duration and args.duration > 0:
            time.sleep(args.duration)
        elif launched is not None:
            print("capturing until the launched app exits (Ctrl+C to stop early)...")
            launched.wait()
        else:
            input("Press Enter to stop the capture...\n")
    except KeyboardInterrupt:
        pass

    stop_evt.set()
    if flusher:
        flusher.join(timeout=(args.post_interval or 0) + 5)
    if screenshot_worker:
        screenshot_worker.join(
            timeout=float(getattr(args, "screenshot_poll_interval", DEFAULT_SCREENSHOT_POLL_INTERVAL)) + 5
        )
    if monitor:
        monitor.stop()
    client_ip = conn_monitor.stop() if conn_monitor else None
    if client_ip:
        print(f"detected client {client_ip} -> {conninfo.classify_network_path(client_ip, args.wg_subnet)}")

    flush(final=True)
    _queue_display_snapshot("after")
    _post_display_samples()
    observed_log_text = "\n".join(observed_log_parts)

    if args.source == "host" and (observed_log_text.strip() or client_ip):
        _enrich_host(hub, sid, observed_log_text, client_ip, args)

    if args.stop_session:
        client.stop_session(hub, sid)
        print("session marked stopped")

    url = f"{hub}/sessions/{sid}"
    print(f"done -> {url}")
    return url


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="asl_collector", description="Apollo Streaming Lab collector")
    p.add_argument("--hub-url", required=True, help="e.g. https://apollo-streaming-lab.<tailnet>.ts.net")
    p.add_argument("--session-id", help="existing session id; omit to attach to a session the "
                                         "host created (auto-picks when only one is awaiting a "
                                         "client, else prompts), or use --create for a new one")
    p.add_argument("--attach-latest", action="store_true", dest="attach_latest",
                   help="attach to the newest session awaiting a client without prompting "
                        "(no session-id copy-paste; ideal for scripted clients)")
    p.add_argument("--create", action="store_true", help="create a new session")
    p.add_argument("--watch", action="store_true",
                   help="run as a long-lived collector: wait for a session the other side "
                        "created, capture into it, then wait for the next one. Idempotent - "
                        "safe to leave running across many tests (typical for the host)")
    p.add_argument("--watch-interval", type=float, default=5.0, dest="watch_interval",
                   help="seconds between hub polls in --watch mode (default 5)")
    p.add_argument("--source", choices=["host", "client"], default="client")
    p.add_argument("--role", choices=["apollo", "moonlight", "artemis"])
    p.add_argument("--log", action="append", default=[], help="log file path/glob (repeatable); "
                   "omit to auto-detect from --source/--role (see logfind.py)")
    p.add_argument("--launch", help="launch this client app (e.g. Artemis/Moonlight) and capture "
                   "its stderr live instead of tailing a buffered log file")
    p.add_argument("--launch-client", action="store_true", dest="launch_client",
                   help="same as --launch but finds the app for --role automatically "
                        "(see appfind.py); capture ends when the app exits")
    p.add_argument("--launch-arg", action="append", default=[], dest="launch_arg",
                   help="argument to pass to --launch (repeatable)")
    p.add_argument("--machine", help="reporting machine name (default: hostname)")
    p.add_argument("--interval", type=float, default=15.0, help="link sample interval seconds (0=off)")
    p.add_argument("--post-interval", type=float, default=30.0, dest="post_interval",
                   help="push logs + link samples to the hub every N seconds during capture so "
                        "the UI updates live (0=only post once when the capture stops)")
    p.add_argument(
        "--screenshot-token",
        default=os.getenv("ASL_SCREENSHOT_TOKEN", ""),
        dest="screenshot_token",
        help="shared secret for screenshot request polling/upload "
             "(default: ASL_SCREENSHOT_TOKEN env var)",
    )
    p.add_argument(
        "--screenshot-poll-interval",
        type=float,
        default=DEFAULT_SCREENSHOT_POLL_INTERVAL,
        dest="screenshot_poll_interval",
        help="seconds between screenshot request polls while capturing (default 3)",
    )
    p.add_argument("--duration", type=int, default=0, help="capture seconds (0=until Enter)")
    p.add_argument("--stop-session", action="store_true", help="mark the session stopped on the hub")
    p.add_argument("--apollo-port", type=int, default=47989,
                   help="Apollo base port for client detection (default 47989)")
    p.add_argument("--wg-subnet", action="append", default=[], dest="wg_subnet",
                   help="WireGuard client subnet (repeatable); a client in it is classified "
                        "remote-WireGuard instead of local-LAN (default: 192.168.2.0/24)")
    # session metadata / observations
    p.add_argument("--name")
    p.add_argument("--host")
    p.add_argument("--client")
    p.add_argument("--comparison-label", dest="comparison_label")
    p.add_argument("--apollo-app", dest="apollo_app")
    p.add_argument("--game-title", dest="game_title")
    p.add_argument("--client-platform", dest="client_platform")
    p.add_argument("--client-version", dest="client_version")
    p.add_argument("--network-path", choices=["local-LAN", "remote-WireGuard", "remote-Tailscale", "remote-WAN"])
    p.add_argument("--codec")
    p.add_argument("--resolution")
    p.add_argument("--fps", type=int)
    p.add_argument("--bitrate-mbps", type=int, dest="bitrate_mbps")
    p.add_argument("--hdr", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    run(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
