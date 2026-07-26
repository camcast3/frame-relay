"""Run iperf3 reverse UDP tests and optionally post results to the hub."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from typing import Any, Optional


def _format_bitrate(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value and value % 1_000_000 == 0:
            return f"{int(value / 1_000_000)}M"
        if value and value % 1_000 == 0:
            return f"{int(value / 1_000)}K"
    return str(value)


def _direction(test_start: dict[str, Any]) -> str:
    protocol = str(test_start.get("protocol") or "").upper()
    transport = protocol if protocol else "unknown"
    if test_start.get("reverse"):
        return f"server->client (reverse {transport})"
    return f"client->server ({transport})"


def parse_iperf3_json(text: str) -> dict[str, Any]:
    """Parse iperf3 -J output into the hub net-test shape."""
    obj = json.loads(text)
    end = obj.get("end") or {}
    summary = end.get("sum") or end.get("sum_received") or end.get("sum_sent") or {}
    test_start = (obj.get("start") or {}).get("test_start") or {}

    bits_per_second = summary.get("bits_per_second")
    throughput_mbps = None
    if isinstance(bits_per_second, (int, float)):
        throughput_mbps = round(bits_per_second / 1_000_000, 2)

    return {
        "throughput_mbps": throughput_mbps,
        "jitter_ms": summary.get("jitter_ms"),
        "loss_pct": summary.get("lost_percent"),
        "direction": _direction(test_start) if test_start else None,
        "bitrate_target": _format_bitrate(test_start.get("target_bitrate")) if test_start else None,
        "raw": text,
    }


def run_iperf3(
    host: str,
    duration: int = 60,
    bitrate: str = "50M",
    reverse: bool = True,
    udp: bool = True,
    iperf_path: str = "iperf3",
) -> dict[str, Any]:
    """Run iperf3 and return parsed JSON output."""
    cmd = [iperf_path, "-c", host, "-t", str(duration), "-J"]
    if udp:
        cmd.append("-u")
    if reverse:
        cmd.append("-R")
    if bitrate:
        cmd.extend(["-b", bitrate])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration + 30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("iperf3 is not installed or not on PATH. Install iperf3 and try again.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"iperf3 timed out after {duration + 30} seconds.") from exc

    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        raise RuntimeError(f"iperf3 failed: {message}")

    return parse_iperf3_json(proc.stdout)


def newest_active_session(hub_url: str) -> Optional[str]:
    """Id of the most recent session that is still running, so a test run needs no id.

    Mirrors how the collectors resolve a session: the operator is already streaming, so the
    session they mean is the active one.
    """
    url = f"{hub_url.rstrip('/')}/api/sessions"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            sessions = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - a missing hub shouldn't crash the test run
        print(f"could not list sessions on {hub_url}: {exc}")
        return None
    for s in sessions:                      # the API returns newest first
        if str(s.get("status", "")).lower() == "active":
            return s.get("id")
    return None


def post_to_hub(hub_url: str, session_id: str, result: dict[str, Any]) -> None:
    """POST an iperf3 result to the hub nettests endpoint."""
    payload = {"tool": "iperf3", **result}
    url = f"{hub_url.rstrip('/')}/api/sessions/{session_id}/nettests"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the sanctioned Apollo iperf3 reverse UDP test.")
    parser.add_argument("--host", required=True, help="iperf3 server host")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--bitrate", default="50M")
    parser.add_argument("--hub-url", help="post the result to this hub")
    parser.add_argument("--session-id",
                        help="session to attach the result to; with --hub-url and no id, the "
                             "newest active session is used")
    args = parser.parse_args()

    # Posting used to require both flags and silently did nothing otherwise, so a run could look
    # successful while the hub never received it.
    if args.session_id and not args.hub_url:
        parser.error("--session-id needs --hub-url to post the result")

    session_id = args.session_id
    if args.hub_url and not session_id:
        session_id = newest_active_session(args.hub_url)
        if not session_id:
            parser.error("no active session on the hub to attach to; start one or pass "
                         "--session-id")
        print(f"attaching result to the newest active session: {session_id}")

    try:
        result = run_iperf3(args.host, duration=args.duration, bitrate=args.bitrate)
    except RuntimeError as exc:
        # A stack trace here buries the one line that matters (usually "iperf3 is not installed"
        # or "connection refused" because nothing is listening on the host).
        print(f"error: {exc}", file=sys.stderr)
        print("hint: install iperf3 on BOTH machines (winget install ar51an.iPerf3, or "
              "apt/dnf install iperf3) and run `iperf3 -s` on the host first.", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(result, indent=2, sort_keys=True))

    if args.hub_url and session_id:
        try:
            post_to_hub(args.hub_url, session_id, result)
        except Exception as exc:  # noqa: BLE001
            print(f"error: could not post to the hub: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print(f"posted to {args.hub_url.rstrip('/')}/sessions/{session_id}")
    else:
        print("not posted to a hub (pass --hub-url to record this against a session)")


if __name__ == "__main__":
    main()
