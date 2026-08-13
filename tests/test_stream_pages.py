"""Stream identity, HDR evidence, and matched comparison pages."""


def _session(client, role, label="cyberpunk-hdr", status="working", rating=4, **extra):
    payload = {
        "name": f"{role} HDR",
        "host": "DOMINO",
        "client": f"{role}-box",
        "network_path": "local-LAN",
        "comparison_label": label,
        "apollo_app": "Playnite",
        "game_title": "Cyberpunk 2077",
        "client_role": role,
        "client_platform": "Windows",
        "requested_settings": {
            "codec": "HEVC",
            "resolution": "3840x2160",
            "fps": 60,
            "bitrate_mbps": 80,
            "hdr": True,
        },
        "codec": "HEVC",
        "resolution": "3840x2160",
        "fps": 60,
        "bitrate_mbps": 80,
        "hdr": True,
        "hdr_details": {
            "requested": True,
            "host_display_hdr": True,
            "encoded_hdr": True,
            "client_display_hdr": status == "working",
            "status": status,
        },
        "visual_assessment": {"rating": rating, "notes": f"{role} result"},
    }
    payload.update(extra)
    response = client.post("/api/sessions", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_stream_evidence_renders(client):
    session = _session(client, "artemis")
    page = client.get(f"/sessions/{session['id']}")
    assert page.status_code == 200
    assert "Stream identity" in page.text
    assert "Cyberpunk 2077" in page.text
    assert "HDR pipeline" in page.text
    assert "Client requested" in page.text


def test_matched_comparison_page_and_api(client):
    label = "cyberpunk-hdr-matched"
    _session(client, "artemis", label=label, status="working", rating=5)
    _session(client, "moonlight", label=label, status="fallback", rating=2)

    api = client.get(f"/api/sessions/comparisons/{label}")
    assert api.status_code == 200
    assert len(api.json()["sessions"]) == 2
    assert api.json()["compatibility"]["compatible"] is True

    page = client.get(f"/comparisons/{label}")
    assert page.status_code == 200
    assert f"Client comparison: {label}" in page.text
    assert "artemis" in page.text
    assert "moonlight" in page.text
    assert "Comparable" in page.text


def test_comparison_flags_control_mismatch(client):
    label = "cyberpunk-hdr-mismatch"
    _session(client, "artemis", label=label)
    _session(
        client,
        "moonlight",
        label=label,
        requested_settings={
            "codec": "AV1",
            "resolution": "3840x2160",
            "fps": 60,
            "bitrate_mbps": 80,
            "hdr": True,
        },
    )
    data = client.get(f"/api/sessions/comparisons/{label}").json()
    assert data["compatibility"]["compatible"] is False
    assert data["compatibility"]["mismatches"]["requested_settings"]["codec"] == ["HEVC", "AV1"]
