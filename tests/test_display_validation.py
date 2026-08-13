"""Virtual-display topology validation."""
from hub import display_validation


def _session(**kw):
    value = {
        "resolution": "3840x2160",
        "fps": 120,
        "hdr": 1,
        "requested_settings": {"resolution": "3840x2160", "fps": 120, "hdr": True},
    }
    value.update(kw)
    return value


def _sample(phase, **kw):
    value = {
        "source": "host",
        "phase": phase,
        "adapter_id": "0:1",
        "source_id": 1,
        "target_id": 2,
        "device_path": "apollo-virtual",
        "friendly_name": "Apollo Virtual Display",
        "is_virtual": 1,
        "primary": 1,
        "width": 3840,
        "height": 2160,
        "refresh_hz": 119.88,
        "hdr_enabled": 1,
    }
    value.update(kw)
    return value


def test_matching_virtual_display_passes():
    samples = [
        _sample("before", device_path="physical", friendly_name="TV", is_virtual=0),
        _sample("during"),
        _sample("after", device_path="physical", friendly_name="TV", is_virtual=0),
    ]
    result = display_validation.summarize(_session(), samples)
    assert result["status"] == "pass"
    assert result["display_name"] == "Apollo Virtual Display"
    assert result["checks"]["virtual_display_active"] is True
    assert result["checks"]["resolution_matches"] is True
    assert result["checks"]["refresh_matches"] is True
    assert result["checks"]["hdr_matches"] is True
    assert result["checks"]["topology_restored_after"] is True


def test_wrong_mode_or_missing_virtual_display_fails():
    result = display_validation.summarize(
        _session(),
        [_sample("during", is_virtual=0, width=1920, height=1080, hdr_enabled=0)],
    )
    assert result["status"] == "fail"
    assert result["checks"]["virtual_display_active"] is False
    assert result["checks"]["resolution_matches"] is False
    assert result["checks"]["hdr_matches"] is False


def test_unknown_identity_is_partial_not_false_success():
    result = display_validation.summarize(
        _session(),
        [_sample("during", is_virtual=None, friendly_name="", device_path="")],
    )
    assert result["status"] == "partial"
    assert result["checks"]["virtual_display_active"] is None


def test_client_display_samples_cannot_drive_host_validation():
    sample = _sample("during")
    sample["source"] = "client"
    result = display_validation.summarize(_session(), [sample])
    assert result["status"] == "partial"
    assert result["checks"]["topology_observed"] is False


def test_no_samples_is_partial_not_failure():
    result = display_validation.summarize(_session(), [])
    assert result["status"] == "partial"


def test_requested_settings_are_used_when_effective_mode_missing():
    result = display_validation.summarize(
        _session(resolution=None, fps=None, hdr=0),
        [_sample("during", refresh_hz=120.0)],
    )
    assert result["expected"] == {
        "resolution": "3840x2160",
        "refresh_hz": 120,
        "hdr": True,
    }


def test_stopped_session_stays_partial_until_teardown_is_observed():
    result = display_validation.summarize(
        _session(status="stopped"),
        [_sample("during")],
    )
    assert result["status"] == "partial"
    assert result["checks"]["topology_restored_after"] is None


def test_session_api_and_page_include_display_validation(client):
    session = client.post(
        "/api/sessions",
        json={
            "name": "display-check",
            "resolution": "3840x2160",
            "fps": 120,
            "hdr": True,
            "requested_settings": {"resolution": "3840x2160", "fps": 120, "hdr": True},
        },
    ).json()
    sid = session["id"]
    response = client.post(
        f"/api/sessions/{sid}/displays",
        json={"samples": [{
            "phase": "during",
            "source": "host",
            "friendly_name": "Apollo Virtual Display",
            "device_path": "apollo-virtual",
            "adapter_id": "0:1",
            "source_id": 1,
            "target_id": 2,
            "is_virtual": True,
            "primary": True,
            "width": 3840,
            "height": 2160,
            "refresh_hz": 119.88,
            "hdr_supported": True,
            "hdr_enabled": True,
        }]},
    )
    assert response.status_code == 200, response.text

    bundle = client.get(f"/api/sessions/{sid}").json()
    assert bundle["display_validation"]["status"] == "pass"
    assert bundle["display_validation"]["display_name"] == "Apollo Virtual Display"

    page = client.get(f"/sessions/{sid}")
    assert page.status_code == 200
    assert "Virtual display validation" in page.text
    assert "Apollo Virtual Display" in page.text
    assert "QueryDisplayConfig" in page.text
