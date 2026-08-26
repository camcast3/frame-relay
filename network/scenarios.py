"""Network-path presets for Apollo streaming tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCENARIOS: dict[str, dict[str, Any]] = {
    "local-LAN": {
        "codec": "HEVC",
        "resolution_fps_guidance": "Start at 1440p/60 or 4K/60 on wired or strong 5 GHz/6 GHz Wi-Fi.",
        "starting_bitrate_mbps": 80,
        "iperf_bitrate": "80M",
        "encoder_knobs": {
            "fec_percentage": 0,
            "lan_encryption_mode": "disabled or auto",
            "wan_encryption_mode": "auto",
        },
        "what_to_watch_for": "Wi-Fi roaming, weak RSSI, packet loss above 5%, or jitter above 1 ms.",
    },
    "remote-Tailscale": {
        "codec": "HEVC",
        "resolution_fps_guidance": "Start at 1080p/60, then raise resolution after loss and jitter are stable.",
        "starting_bitrate_mbps": 35,
        "iperf_bitrate": "50M",
        "encoder_knobs": {
            "fec_percentage": 10,
            "lan_encryption_mode": "auto",
            "wan_encryption_mode": "enabled",
        },
        "what_to_watch_for": "DERP relay fallback, MTU issues, loss above 5%, or jitter above 1 ms.",
    },
    "remote-WireGuard": {
        "codec": "HEVC",
        "resolution_fps_guidance": "Start at 1080p/60; WireGuard adds ~60-80 byte overhead so watch for MTU-driven loss.",
        "starting_bitrate_mbps": 35,
        "iperf_bitrate": "50M",
        "encoder_knobs": {
            "fec_percentage": 15,
            "lan_encryption_mode": "auto",
            "wan_encryption_mode": "enabled",
        },
        "what_to_watch_for": "Tunnel MTU (try host MTU ~1420), router/uplink saturation, loss above 5%, jitter above 1 ms.",
    },
    "remote-WAN": {
        "codec": "HEVC",
        "resolution_fps_guidance": "Start at 1080p/60 or 720p/60 on constrained uplinks.",
        "starting_bitrate_mbps": 25,
        "iperf_bitrate": "30M",
        "encoder_knobs": {
            "fec_percentage": 20,
            "lan_encryption_mode": "auto",
            "wan_encryption_mode": "enabled",
        },
        "what_to_watch_for": "Upload saturation, bufferbloat, NAT/firewall issues, packet loss, and jitter spikes.",
    },
}


def list_scenarios() -> dict[str, dict[str, Any]]:
    return deepcopy(SCENARIOS)


def get_scenario(name: str) -> dict[str, Any]:
    return deepcopy(SCENARIOS[name])
