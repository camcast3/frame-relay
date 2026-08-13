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
    assert r.json()["screenshot_requests_enabled"] is True


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
    """"Awaiting a client" keys off client *logs*, not the client name field.

    The host collector fills the client name from the live connection while it runs, so a
    session must stay attachable until a client collector actually posts something.
    """
    named = _create(client, name="named-but-unattached")          # client name set, no logs
    r = client.post("/api/sessions", json={"name": "open", "host": "DOMINO", "client": None})
    unnamed = r.json()                                            # no client name, no logs
    attached = _create(client, name="already-attached")
    client.post(f"/api/sessions/{attached['id']}/logs",
                json={"source": "client", "role": "moonlight", "content": "hello"})
    stopped = _create(client, name="finished")
    client.post(f"/api/sessions/{stopped['id']}/stop")

    all_ids = {s["id"] for s in client.get("/api/sessions").json()}
    assert {named["id"], unnamed["id"], attached["id"], stopped["id"]} <= all_ids

    awaiting_ids = {s["id"] for s in
                    client.get("/api/sessions", params={"awaiting_client": "true"}).json()}
    # a pre-filled client name must NOT hide the session from the client collector
    assert named["id"] in awaiting_ids
    assert unnamed["id"] in awaiting_ids
    # once a client has posted logs, or the session is stopped, it is no longer awaiting
    assert attached["id"] not in awaiting_ids
    assert stopped["id"] not in awaiting_ids


def test_awaiting_host_filter(client):
    """Mirror image: a host watcher picks up sessions the client created."""
    fresh = _create(client, name="client-made")
    with_host = _create(client, name="host-attached")
    client.post(f"/api/sessions/{with_host['id']}/logs",
                json={"source": "host", "role": "apollo", "content": "Info: started"})
    stopped = _create(client, name="finished")
    client.post(f"/api/sessions/{stopped['id']}/stop")

    awaiting_ids = {s["id"] for s in
                    client.get("/api/sessions", params={"awaiting_host": "true"}).json()}
    assert fresh["id"] in awaiting_ids
    assert with_host["id"] not in awaiting_ids
    assert stopped["id"] not in awaiting_ids

    # a session can await both sides at once, and posting one side does not affect the other
    both = {s["id"] for s in client.get(
        "/api/sessions", params={"awaiting_host": "true", "awaiting_client": "true"}).json()}
    assert fresh["id"] in both
    assert with_host["id"] not in both


def test_pages_render(client):
    s = _create(client, name="render-test")
    assert client.get("/").status_code == 200
    assert client.get("/sessions/new").status_code == 200
    r = client.get(f"/sessions/{s['id']}")
    assert r.status_code == 200
    assert "render-test" in r.text
    assert "Copilot analysis" in r.text
