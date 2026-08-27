from __future__ import annotations

"""Unit tests for deriving metadata from Apollo host logs."""

from frame_relay_collector import hostmeta
from conftest import SAMPLES


def test_parse_apollo_metadata_from_real_sample():
    d = hostmeta.parse_apollo_metadata((SAMPLES / "apollo-metadata.log").read_text())
    assert d["codec"] == "H.264"          # "Found H.264 encoder" wins over the failed amf attempt
    assert d["resolution"] == "2560x1600"
    assert d["fps"] == 60
    assert d["bitrate_mbps"] == 44         # 44000 kbps
    assert d["hdr"] is False
    assert d["requested_settings"] == {"fps": 60, "hdr": False}
    assert d["hdr_details"] == {
        "host_display_hdr": False,
        "evidence": ["Apollo log: Display is HDR: false"],
        "requested": False,
        "confidence": 0.9,
    }


def test_parse_apollo_metadata_rich_sample():
    d = hostmeta.parse_apollo_metadata((SAMPLES / "apollo-metadata-rich.log").read_text())
    assert d["apollo_app"] == "Steam Big Picture"
    assert d["game_title"] == "Elden Ring"
    assert d["codec"] == "AV1"
    assert d["resolution"] == "3840x2160"
    assert d["fps"] == 120
    assert d["bitrate_mbps"] == 82
    assert d["hdr"] is True
    assert d["requested_settings"] == {
        "codec": "AV1",
        "resolution": "3840x2160",
        "fps": 120,
        "bitrate_mbps": 85,
        "hdr": True,
    }
    assert d["hdr_details"] == {
        "host_display_hdr": True,
        "evidence": [
            "Apollo log: Display is HDR: true",
            "Apollo log: Color coding: HDR (Rec. 2020 + SMPTE 2084 PQ + 10-bit)",
        ],
        "requested": True,
        "encoded_hdr": True,
        "color_primaries": "Rec. 2020",
        "transfer_function": "SMPTE 2084 PQ",
        "bit_depth": 10,
        "confidence": 0.9,
    }


def test_normalize_codec():
    assert hostmeta.normalize_codec("h264_amf") == "H.264"
    assert hostmeta.normalize_codec("libx264") == "H.264"
    assert hostmeta.normalize_codec("hevc_amf") == "HEVC"
    assert hostmeta.normalize_codec("av1_nvenc") == "AV1"
    assert hostmeta.normalize_codec("something") is None


def test_parse_apollo_metadata_repeated_patterns_take_last():
    text = "\n".join([
        "[..]: Info: Selected application [Old App] id [1]",
        "[..]: Info: Game title [Old Game]",
        "[..]: Info: Client Requested codec [h264]",
        "[..]: Info: Client Requested bitrate is [40000kbps]",
        "[..]: Info: Requested frame rate [60fps]",
        "[..]: Info: Client dynamicRange: 0, Display is HDR: false",
        "[..]: Info: Creating encoder [h264_amf]",
        "[..]: Info: Desktop resolution [1920x1080]",
        "[..]: Info: Host Streaming bitrate is [38000kbps]",
        "[..]: Info: Launching application [New App] id [2]",
        "[..]: Info: Process title [NewGame.exe]",
        "[..]: Info: Client Requested codec [hevc]",
        "[..]: Info: Client Requested stream resolution [2560x1440]",
        "[..]: Info: Client Requested bitrate is [75000kbps]",
        "[..]: Info: Requested frame rate [120fps]",
        "[..]: Info: Client dynamicRange: 1, Display is HDR: true",
        "[..]: Info: Color coding: HDR (Rec. 2020 + SMPTE 2084 PQ + 10-bit)",
        "[..]: Info: Found HEVC encoder: hevc_nvenc [hardware]",
        "[..]: Info: Desktop resolution [2560x1440]",
        "[..]: Info: Host Streaming bitrate is [70000kbps]",
    ])
    d = hostmeta.parse_apollo_metadata(text)
    assert d["apollo_app"] == "New App"
    assert d["game_title"] == "NewGame.exe"
    assert d["codec"] == "HEVC"
    assert d["resolution"] == "2560x1440"
    assert d["fps"] == 120
    assert d["bitrate_mbps"] == 70
    assert d["hdr"] is True
    assert d["requested_settings"] == {
        "codec": "HEVC",
        "resolution": "2560x1440",
        "fps": 120,
        "bitrate_mbps": 75,
        "hdr": True,
    }


def test_applications_for_line_is_not_treated_as_selected_app():
    text = "[..]: Info: Applications for [couch]\n[..]: Info: CLIENT CONNECTED"
    assert hostmeta.parse_apollo_metadata(text) == {}


def test_codec_hevc_and_hdr_true():
    text = (
        "[..]: Info: Desktop resolution [3840x2160]\n"
        "[..]: Info: Requested frame rate [120fps]\n"
        "[..]: Info: Client dynamicRange: 1, Display is HDR: true\n"
        "[..]: Info: Creating encoder [hevc_amf]\n"
        "[..]: Info: Host Streaming bitrate is [150000kbps]\n"
    )
    d = hostmeta.parse_apollo_metadata(text)
    assert d["codec"] == "HEVC"
    assert d["resolution"] == "3840x2160"
    assert d["fps"] == 120
    assert d["bitrate_mbps"] == 150
    assert d["hdr"] is True


def test_empty_log_returns_empty():
    assert hostmeta.parse_apollo_metadata("nothing useful here") == {}
