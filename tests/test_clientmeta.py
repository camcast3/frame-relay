from __future__ import annotations

"""Unit tests for deriving metadata from Moonlight/Artemis client logs."""

from asl_collector import clientmeta
from conftest import SAMPLES


def test_parse_moonlight_metadata_sample():
    d = clientmeta.parse_client_metadata((SAMPLES / "moonlight-metadata.log").read_text(),
                                         "moonlight")
    assert d["client_version"] == "6.1.0"
    assert d["requested_settings"] == {
        "resolution": "2560x1440",
        "fps": 120,
        "bitrate_mbps": 85,
        "codec": "AV1",
        "hdr": True,
    }
    assert d["hdr_details"] == {
        "requested": True,
        "client_display_hdr": True,
        "client_renderer": "D3D11",
        "client_decoder": "FFmpeg-based",
        "evidence": [
            "Client log: Color coding: HDR (Rec. 2020 + SMPTE 2084 PQ + 10-bit)",
            "[2026-07-23 10:00:04] Qt Warning: HDR fallback to SDR because display does not support it",
        ],
        "encoded_hdr": True,
        "color_primaries": "Rec. 2020",
        "transfer_function": "SMPTE 2084 PQ",
        "bit_depth": 10,
        "tone_mapping": "disabled",
        "status": "fallback",
        "confidence": 0.9,
    }


def test_parse_artemis_metadata_sample():
    d = clientmeta.parse_client_metadata((SAMPLES / "artemis-metadata.log").read_text(),
                                         "artemis")
    assert d["client_version"] == "0.3.2"
    assert d["requested_settings"] == {
        "resolution": "1920x1080",
        "fps": 60,
        "bitrate_mbps": 45,
        "codec": "H.264",
        "hdr": False,
    }
    assert d["hdr_details"] == {
        "requested": False,
        "client_display_hdr": False,
        "client_renderer": "Vulkan",
        "client_decoder": "D3D11VA",
        "evidence": [
            "Client log: Color coding: SDR (Rec. 709 + Gamma 2.2 + 8-bit)",
            "00:00:03 - Qt Warning: HDR disabled by client setting",
        ],
        "encoded_hdr": False,
        "color_primaries": "Rec. 709",
        "transfer_function": "Gamma 2.2",
        "bit_depth": 8,
        "tone_mapping": "passthrough",
        "confidence": 0.9,
    }


def test_parse_client_metadata_partial_and_absent_patterns():
    text = (
        "00:00:01 - Qt Info: Moonlight version: 6.1.1\n"
        "00:00:02 - Qt Info: Setting stream width to 2560\n"
        "00:00:03 - Qt Info: Setting frame rate to 60 FPS\n"
    )
    d = clientmeta.parse_client_metadata(text, "moonlight")
    assert d["client_version"] == "6.1.1"
    assert d["requested_settings"] == {"fps": 60}
    assert "hdr_details" not in d


def test_parse_client_metadata_repeated_patterns_take_last():
    text = "\n".join([
        "00:00:00 - Qt Info: Artemis version: 0.3.1",
        '00:00:01 - Qt Debug: NvHTTP::openConnection - URL: "https://host:47984" Arguments: "width=1280&height=720&fps=30&bitrate=15000&hdrMode=0&codec=h264"',
        "00:00:02 - SDL Info (0): Using decoder: software",
        "00:00:03 - Qt Info: Dynamic range: SDR",
        '00:00:04 - Qt Debug: NvHTTP::openConnection - URL: "https://host:47984" Arguments: "width=2560&height=1440&fps=120&bitrate=85000&hdrMode=1&codec=av1"',
        "00:00:05 - SDL Info (0): Using decoder: D3D11VA",
        "00:00:06 - SDL Info (0): Chosen renderer: Vulkan",
        "00:00:07 - Qt Info: Dynamic range: HDR",
        "00:00:08 - Qt Info: Display is HDR: true",
    ])
    d = clientmeta.parse_client_metadata(text, "artemis")
    assert d["client_version"] == "0.3.1"
    assert d["requested_settings"] == {
        "resolution": "2560x1440",
        "fps": 120,
        "bitrate_mbps": 85,
        "codec": "AV1",
        "hdr": True,
    }
    assert d["hdr_details"]["requested"] is True
    assert d["hdr_details"]["client_decoder"] == "D3D11VA"
    assert d["hdr_details"]["client_renderer"] == "Vulkan"
    assert d["hdr_details"]["client_display_hdr"] is True
    assert "status" not in d["hdr_details"]  # no encoded-color evidence in this partial log


def test_parse_client_metadata_empty_log_returns_empty():
    assert clientmeta.parse_client_metadata("nothing useful here", "moonlight") == {}
