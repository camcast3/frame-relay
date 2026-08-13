"""Copilot findings from Windows display-topology validation."""
from hub import copilot


def test_display_mode_and_hdr_mismatches_are_reported():
    ctx = {
        "display_samples": [{"phase": "during"}],
        "display_validation": {
            "checks": {
                "topology_observed": True,
                "virtual_display_active": True,
                "resolution_matches": False,
                "refresh_matches": False,
                "hdr_matches": False,
                "topology_restored_after": False,
            },
            "expected": {"resolution": "3840x2160", "refresh_hz": 120, "hdr": True},
            "actual": {"resolution": "1920x1080", "refresh_hz": 60.0, "hdr": False},
        },
    }
    findings = copilot._display_findings(ctx)
    joined = "\n".join(findings)
    assert "3840x2160" in joined and "1920x1080" in joined
    assert "120" in joined and "60.0" in joined
    assert "Advanced Color" in joined
    assert "did not return" in joined


def test_unknown_virtual_identity_is_not_reported_as_success():
    ctx = {
        "display_samples": [{"phase": "during"}],
        "display_validation": {
            "checks": {
                "topology_observed": True,
                "virtual_display_active": None,
            },
        },
    }
    assert "could not be confidently" in "\n".join(copilot._display_findings(ctx))


def test_no_samples_add_no_display_findings():
    assert copilot._display_findings({"display_samples": []}) == []


def test_missing_during_topology_does_not_claim_unknown_target():
    ctx = {
        "display_samples": [{"phase": "before"}],
        "display_validation": {
            "checks": {
                "topology_observed": False,
                "virtual_display_active": None,
            },
        },
    }
    findings = copilot._display_findings(ctx)
    assert findings == ["No active Windows display topology was observed during the stream."]
