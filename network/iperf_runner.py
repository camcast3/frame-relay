"""Run iperf3 reverse UDP tests and optionally post results to the hub."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from typing import Any


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
    parser.add_argument("--hub-url")
    parser.add_argument("--session-id")
    args = parser.parse_args()

    result = run_iperf3(args.host, duration=args.duration, bitrate=args.bitrate)
    if args.hub_url and args.session_id:
        post_to_hub(args.hub_url, args.session_id, result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
