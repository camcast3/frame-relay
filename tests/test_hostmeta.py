"""Unit tests for deriving session metadata from an Apollo host log."""
from asl_collector import hostmeta
from conftest import SAMPLES


def test_parse_apollo_metadata_from_real_sample():
    d = hostmeta.parse_apollo_metadata((SAMPLES / "apollo-metadata.log").read_text())
    assert d["codec"] == "H.264"          # "Found H.264 encoder" wins over the failed amf attempt
    assert d["resolution"] == "2560x1600"
    assert d["fps"] == 60
    assert d["bitrate_mbps"] == 44         # 44000 kbps
    assert d["hdr"] is False


def test_normalize_codec():
    assert hostmeta.normalize_codec("h264_amf") == "H.264"
    assert hostmeta.normalize_codec("libx264") == "H.264"
    assert hostmeta.normalize_codec("hevc_amf") == "HEVC"
    assert hostmeta.normalize_codec("av1_nvenc") == "AV1"
    assert hostmeta.normalize_codec("something") is None


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
