"""Session capture orchestrator + CLI.

Typical use on a machine under test (run with the system Python; stdlib only):

    # Apollo host
    python -m asl_collector --hub-url https://apollo-streaming-lab.<tailnet>.ts.net \
        --session-id 20260723T101951-ab12 --source host --role apollo \
        --log "C:\\Program Files\\Apollo\\config\\sunshine.log" --interval 15

    # Moonlight client (Linux); create the session on the fly
    python3 -m asl_collector --hub-url https://apollo-streaming-lab.<tailnet>.ts.net \
        --create --name "couch LAN HEVC" --host DOMINO --client couch \
        --network-path local-LAN --source client --role moonlight \
        --log ~/.config/Moonlight*/Moonlight.log --interval 15 --duration 0
"""
from __future__ import annotations

import argparse
import glob
import platform
import sys
from datetime import datetime, timezone
from typing import Optional

from . import client, conninfo, hostmeta, logslice
from .netmon import LinkMonitor


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expand(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths or []:
        matches = glob.glob(p)
        out.extend(matches or [p])
    return out


def _enrich_host(hub: str, sid: str, log_text: str, client_ip: Optional[str],
                 args: argparse.Namespace) -> None:
    """Fill blank session metadata from the Apollo log + the live client connection.

    Log-derived: codec/resolution/fps/bitrate/hdr. Connection-derived: client (IP) and
    network_path (LAN / Tailscale / WAN). Only fills blanks - never overrides a value passed on
    the CLI or already set on the session (e.g. entered in the UI).
    """
    derived = hostmeta.parse_apollo_metadata(log_text) if log_text.strip() else {}
    net_path = conninfo.classify_network_path(client_ip) if client_ip else None
    current = client.get_session(hub, sid) or {}
    patch: dict[str, object] = {}
    for field in ("codec", "resolution", "fps", "bitrate_mbps"):
        if derived.get(field) is not None and getattr(args, field) is None and not current.get(field):
            patch[field] = derived[field]
    if derived.get("hdr") and "--hdr" not in sys.argv and not current.get("hdr"):
        patch["hdr"] = True
    if client_ip and args.client is None and not current.get("client"):
        patch["client"] = client_ip
    if net_path and args.network_path is None and not current.get("network_path"):
        patch["network_path"] = net_path
    if patch:
        client.patch_session(hub, sid, patch)
        print(f"auto-filled: {patch}")


def run(args: argparse.Namespace) -> str:
    hub = args.hub_url.rstrip("/")
    machine = args.machine or platform.node()
    role = args.role or ("apollo" if args.source == "host" else "moonlight")

    sid = args.session_id
    if not sid:
        if not args.create:
            raise SystemExit("provide --session-id or --create")
        # Default host/client to this machine's name based on which side we're capturing.
        default_host = args.host or (machine if args.source == "host" else None)
        default_client = args.client or (machine if args.source == "client" else None)
        sid = client.create_session(hub, {
            "name": args.name, "host": default_host, "client": default_client,
            "network_path": args.network_path, "codec": args.codec,
            "resolution": args.resolution, "fps": args.fps,
            "bitrate_mbps": args.bitrate_mbps, "hdr": args.hdr,
        })
        print(f"created session {sid}")

    logs = _expand(args.log)
    start = _now()
    offsets = {path: logslice.file_offset(path) for path in logs}

    monitor = None
    conn_monitor = None
    if args.interval > 0:
        monitor = LinkMonitor(source=args.source, machine=machine, interval=args.interval)
        monitor.start()
        if args.source == "host":
            conn_monitor = conninfo.ClientMonitor(conninfo.apollo_ports(args.apollo_port), args.interval)
            conn_monitor.start()

    print(f"capturing session {sid} ({args.source}/{role}) on {machine} - "
          f"{'sampling link every %ss' % args.interval if monitor else 'no link sampling'}")
    try:
        if args.duration and args.duration > 0:
            import time
            time.sleep(args.duration)
        else:
            input("Press Enter to stop the capture...\n")
    except KeyboardInterrupt:
        pass

    stop = _now()
    samples = monitor.stop() if monitor else []
    client_ip = conn_monitor.stop() if conn_monitor else None
    if client_ip:
        print(f"detected client {client_ip} -> {conninfo.classify_network_path(client_ip)}")

    host_log_text = ""
    for path in logs:
        content = logslice.read_since(path, offsets.get(path, 0))
        if not content.strip():
            content = logslice.slice_file(path, start, stop)
        if content.strip():
            client.post_log(hub, sid, args.source, role, content, machine)
            print(f"posted {len(content.splitlines())} log lines from {path}")
            if args.source == "host":
                host_log_text += content + "\n"

    if samples:
        added = client.post_links(hub, sid, samples)
        aps = {s.get("bssid") for s in samples if s.get("bssid")}
        print(f"posted {added} link samples ({len(aps)} distinct AP(s))")

    if args.source == "host" and (host_log_text.strip() or client_ip):
        _enrich_host(hub, sid, host_log_text, client_ip, args)

    if args.stop_session:
        client.stop_session(hub, sid)
        print("session marked stopped")

    url = f"{hub}/sessions/{sid}"
    print(f"done -> {url}")
    return url


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="asl_collector", description="Apollo Streaming Lab collector")
    p.add_argument("--hub-url", required=True, help="e.g. https://apollo-streaming-lab.<tailnet>.ts.net")
    p.add_argument("--session-id", help="existing session id; omit with --create")
    p.add_argument("--create", action="store_true", help="create a new session")
    p.add_argument("--source", choices=["host", "client"], default="client")
    p.add_argument("--role", choices=["apollo", "moonlight", "artemis"])
    p.add_argument("--log", action="append", default=[], help="log file path/glob (repeatable)")
    p.add_argument("--machine", help="reporting machine name (default: hostname)")
    p.add_argument("--interval", type=float, default=15.0, help="link sample interval seconds (0=off)")
    p.add_argument("--duration", type=int, default=0, help="capture seconds (0=until Enter)")
    p.add_argument("--stop-session", action="store_true", help="mark the session stopped on the hub")
    p.add_argument("--apollo-port", type=int, default=47989,
                   help="Apollo base port for client detection (default 47989)")
    # metadata used only with --create
    p.add_argument("--name")
    p.add_argument("--host")
    p.add_argument("--client")
    p.add_argument("--network-path", choices=["local-LAN", "remote-Tailscale", "remote-WAN"])
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
