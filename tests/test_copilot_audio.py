"""Analyzer rules for audio dropouts and log-noise filtering."""

from hub import copilot


def _ctx(host_log: str = "", client_log: str = "") -> dict:
    return {
        "scenario": {"network_path": "local-LAN"},
        "net_tests": [],
        "link_samples": [],
        "host_log_tail": host_log,
        "client_log_tail": client_log,
    }


def test_out_of_sequence_audio_is_detected():
    client_log = (
        "00:00:11 - SDL Info (0): Leaving fast audio recovery mode after OOS audio data (863 < 864)\n"
        "00:02:31 - SDL Info (0): Leaving fast audio recovery mode after OOS audio data (912 < 913)\n"
    )
    net = copilot.analyze_signals(_ctx(client_log=client_log))["network"]
    assert any("out-of-sequence audio 2x" in n for n in net)

    diag = copilot._mock(_ctx(client_log=client_log), None)
    assert "Audio packet loss" in diag


def test_surround_opus_is_flagged():
    host_log = "[15:44:55]: Info: Opus initialized: 48 kHz, 8 channels, 2048 kbps (total), LOWDELAY"
    net = copilot.analyze_signals(_ctx(host_log=host_log))["network"]
    assert any("8-channel (surround) Opus" in n for n in net)


def test_stereo_opus_is_not_flagged():
    host_log = "[15:55:32]: Info: Opus initialized: 48 kHz, 2 channels, 512 kbps (total), LOWDELAY"
    net = copilot.analyze_signals(_ctx(host_log=host_log))["network"]
    assert not any("Opus" in n for n in net)


def test_benign_encoder_probe_lines_are_not_flagged():
    """Apollo's encoder probe deliberately provokes failures; it must not drown real signal."""
    host_log = "\n".join([
        "Info: // Testing for available encoders, this may generate errors. "
        "You can safely ignore those errors. //",
        "Info: Encoder [nvenc] is not supported on this GPU",
        "Info: Encoder [quicksync] is not supported on this GPU",
        "Info: nvprefs: NvAPI_Initialize() failed, ignore if you don't have NVIDIA video card",
        "Info: Client dynamicRange: 1, Display is HDR: true",
        "Info: Color coding: HDR (Rec. 2020 + SMPTE 2084 PQ)",
        "Info: // Ignore any errors mentioned above, they are not relevant. //",
    ])
    assert copilot._log_findings(host_log) == []


def test_real_errors_still_surface():
    host_log = "\n".join([
        "Info: Encoder [nvenc] is not supported on this GPU",       # benign
        "Error: Failed to create encoder D3D11 device [0x887A0004]",  # real
    ])
    hits = copilot._log_findings(host_log)
    assert len(hits) == 1
    assert "Failed to create encoder D3D11 device" in hits[0]


def test_client_decoder_noise_filtered_but_errors_kept():
    client_log = "\n".join([
        "00:00:03 - FFmpeg: [av1 @ 0x1] Decoder GUIDs reported as supported:",  # benign
        "00:00:03 - SDL Info (0): FFmpeg-based video decoder chosen",           # benign
        "00:00:03 - SDL Info (0): Decoder texture access: copy (fence: no)",    # benign
        "00:00:09 - SDL Error (0): Video decoder failed to initialize",         # real
    ])
    hits = copilot._log_findings(client_log)
    assert len(hits) == 1
    assert "Video decoder failed to initialize" in hits[0]


def test_optional_endpoint_probes_are_not_flagged():
    """Artemis probes command endpoints Apollo lacks; the 404s happen on every connect."""
    client_log = "\n".join([
        '00:00:04 - Qt Warning: "servercommands" request failed with error: '
        'QNetworkReply::ContentNotFoundError',
        '00:00:04 - Qt Debug: ServerCommandManager::fetchAvailableCommands: Network error for '
        '"commands" : "Error transferring https://h/commands - server replied: Not Found"',
        '00:00:06 - SDL Info (0): Reference frame invalidation is not supported by this host',
        '00:00:06 - Qt Debug: NvHTTP::openConnection - URL: "https://h:47984" '
        'Arguments: "hdrMode=1&codec=av1"',
    ])
    assert copilot._log_findings(client_log) == []
