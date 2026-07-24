"""End-to-end API + page-render tests for the hub."""


def _create(client, **kw):
    payload = {"name": "t", "host": "DOMINO", "client": "couch",
               "network_path": "local-LAN", "codec": "HEVC"}
    payload.update(kw)
    r = client.post("/api/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["copilot_backend"] == "mock"


def test_session_lifecycle(client):
    s = _create(client)
    sid = s["id"]
    assert s["status"] == "active"

    # logs from host + client
    assert client.post(f"/api/sessions/{sid}/logs",
                       json={"source": "host", "role": "apollo",
                             "content": "Info: Client connected\nError: encoder failed"}).status_code == 200
    assert client.post(f"/api/sessions/{sid}/logs",
                       json={"source": "client", "role": "moonlight",
                             "content": "Connection established\nWARN: decoder latency high"}).status_code == 200

    # link samples showing a roam + weak signal
    samples = {"samples": [
        {"source": "client", "link_type": "wifi", "ssid": "Home", "bssid": "aa:bb:cc:00:00:01",
         "rssi": -55, "band": "5GHz", "channel": "44", "link_speed": "866 Mbps", "sampled_at": "2026-07-23T10:00:00Z"},
        {"source": "client", "link_type": "wifi", "ssid": "Home", "bssid": "aa:bb:cc:00:00:02",
         "rssi": -75, "band": "5GHz", "channel": "149", "link_speed": "433 Mbps", "sampled_at": "2026-07-23T10:00:30Z"},
    ]}
    r = client.post(f"/api/sessions/{sid}/links", json=samples)
    assert r.json()["added"] == 2

    # a failing network test
    assert client.post(f"/api/sessions/{sid}/nettests",
                       json={"direction": "server->client", "jitter_ms": 3.2, "loss_pct": 9.0,
                             "throughput_mbps": 40}).status_code == 200

    # bundle reflects everything
    b = client.get(f"/api/sessions/{sid}").json()
    assert len(b["host_logs"]) == 1 and len(b["client_logs"]) == 1
    assert len(b["link_samples"]) == 2 and len(b["net_tests"]) == 1

    # analyze (mock) should surface roam + loss + log errors
    diag = client.post(f"/api/sessions/{sid}/analyze").json()["diagnosis"]
    assert "roam" in diag.lower()
    assert "loss" in diag.lower()
    assert "encoder failed" in diag

    # chat
    reply = client.post(f"/api/sessions/{sid}/chat", json={"message": "why stutter?"}).json()["reply"]
    assert reply
    assert len(client.get(f"/api/sessions/{sid}/chat").json()) == 2

    # notes + outcome
    assert client.patch(f"/api/sessions/{sid}", json={"notes": "hi", "outcome": "fail"}).status_code == 200
    assert client.get(f"/api/sessions/{sid}").json()["session"]["outcome"] == "fail"

    # stop + delete
    assert client.post(f"/api/sessions/{sid}/stop").json()["status"] == "stopped"
    assert client.delete(f"/api/sessions/{sid}").json()["ok"] is True
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_patch_metadata(client):
    s = _create(client, codec=None)
    sid = s["id"]
    client.patch(f"/api/sessions/{sid}", json={
        "codec": "H.264", "resolution": "2560x1600", "fps": 60, "bitrate_mbps": 44, "hdr": True})
    got = client.get(f"/api/sessions/{sid}").json()["session"]
    assert got["codec"] == "H.264"
    assert got["resolution"] == "2560x1600"
    assert got["fps"] == 60
    assert got["bitrate_mbps"] == 44
    assert got["hdr"] == 1


def test_awaiting_client_filter(client):
    with_client = _create(client, name="joined")
    r = client.post("/api/sessions", json={"name": "open", "host": "DOMINO", "client": None})
    no_client = r.json()

    all_ids = {s["id"] for s in client.get("/api/sessions").json()}
    assert with_client["id"] in all_ids and no_client["id"] in all_ids

    awaiting = client.get("/api/sessions", params={"awaiting_client": "true"}).json()
    awaiting_ids = {s["id"] for s in awaiting}
    assert no_client["id"] in awaiting_ids
    assert with_client["id"] not in awaiting_ids


def test_pages_render(client):
    s = _create(client, name="render-test")
    assert client.get("/").status_code == 200
    assert client.get("/sessions/new").status_code == 200
    r = client.get(f"/sessions/{s['id']}")
    assert r.status_code == 200
    assert "render-test" in r.text
    assert "Copilot analysis" in r.text
