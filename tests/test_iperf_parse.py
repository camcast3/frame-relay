"""Tests for network iperf parsing and scenario presets."""

import json

from network.iperf_runner import parse_iperf3_json
from network.scenarios import get_scenario, list_scenarios


IPERF3_UDP_REVERSE_SAMPLE = json.dumps(
    {
        "start": {
            "test_start": {
                "protocol": "UDP",
                "duration": 60,
                "reverse": 1,
                "target_bitrate": 50000000,
            }
        },
        "end": {
            "sum": {
                "seconds": 60.000145,
                "bytes": 375925000,
                "bits_per_second": 50123456.7,
                "jitter_ms": 0.321,
                "lost_packets": 42,
                "packets": 10000,
                "lost_percent": 0.42,
                "sender": False,
            }
        },
    }
)


def test_parse_iperf3_udp_reverse_summary():
    result = parse_iperf3_json(IPERF3_UDP_REVERSE_SAMPLE)

    assert result["throughput_mbps"] == 50.12
    assert result["jitter_ms"] == 0.321
    assert result["loss_pct"] == 0.42
    assert result["direction"] == "server->client (reverse UDP)"
    assert result["bitrate_target"] == "50M"
    assert result["raw"] == IPERF3_UDP_REVERSE_SAMPLE


def test_parse_iperf3_missing_keys_does_not_crash():
    result = parse_iperf3_json("{}")

    assert result["throughput_mbps"] is None
    assert result["jitter_ms"] is None
    assert result["loss_pct"] is None
    assert result["direction"] is None
    assert result["bitrate_target"] is None


def test_scenarios_include_hub_network_paths():
    names = set(list_scenarios())

    assert names == {"local-LAN", "remote-WireGuard", "remote-Tailscale", "remote-WAN"}
    for name in names:
        assert get_scenario(name)
