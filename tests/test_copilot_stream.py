"""Structured stream/HDR and matched-client findings."""
from hub import copilot
from hub.routers import analysis


def _ctx(**scenario):
    base = {
        "scenario": scenario,
        "net_tests": [],
        "link_samples": [],
        "host_log_tail": "",
        "client_log_tail": "",
        "related_sessions": [],
    }
    return base


def test_requested_effective_and_hdr_mismatches():
    ctx = _ctx(
        requested_settings={"codec": "AV1", "hdr": True},
        codec="HEVC",
        hdr=True,
        hdr_details={
            "host_display_hdr": False,
            "encoded_hdr": False,
            "client_display_hdr": False,
            "status": "fallback",
        },
    )
    findings = copilot.analyze_signals(ctx)["stream"]
    joined = "\n".join(findings)
    assert "requested codec AV1" in joined
    assert "host display was SDR" in joined
    assert "encoded SDR" in joined
    assert "fallback" in joined


def test_matched_client_hdr_difference():
    ctx = _ctx(
        comparison_label="game-hdr",
        client_role="artemis",
        hdr_details={"status": "working"},
        visual_assessment={"rating": 5},
    )
    ctx["related_sessions"] = [{
        "id": "peer",
        "comparison_label": "game-hdr",
        "client_role": "moonlight",
        "hdr_details": {"status": "fallback"},
        "visual_assessment": {"rating": 2},
    }]
    findings = copilot.analyze_signals(ctx)["comparison"]
    assert any("artemis HDR result is working" in f for f in findings)
    assert any("5/5" in f and "2/5" in f for f in findings)


def test_analysis_filters_incompatible_same_label_peers(monkeypatch):
    current = {
        "id": "current",
        "comparison_label": "game-hdr",
        "host": "DOMINO",
        "network_path": "local-LAN",
        "requested_settings": {"codec": "HEVC", "hdr": True},
    }
    compatible = {
        "id": "compatible",
        "comparison_label": "game-hdr",
        "host": "DOMINO",
        "network_path": "local-LAN",
        "requested_settings": {"codec": "HEVC", "hdr": True},
    }
    incompatible = {
        "id": "incompatible",
        "comparison_label": "game-hdr",
        "host": "DOMINO",
        "network_path": "local-LAN",
        "requested_settings": {"codec": "AV1", "hdr": True},
    }
    monkeypatch.setattr(
        analysis.service, "get_comparison_sessions",
        lambda label: [current, compatible, incompatible],
    )
    assert analysis._comparison_peers({"session": current}) == [compatible]
