"""HTML and bundle tests for the screenshot comparison session card."""
from __future__ import annotations

from base64 import b64decode
from html.parser import HTMLParser

from hub import config

PNG_BYTES = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV7kAAAAASUVORK5CYII="
)


class _IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements: dict[str, dict[str, object]] = {}
        self._stack: list[str | None] = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        element_id = attr_map.get("id")
        if element_id:
            self.elements[element_id] = {"tag": tag, "attrs": attr_map, "text": []}
        self._stack.append(element_id)

    def handle_startendtag(self, tag, attrs):
        attr_map = dict(attrs)
        element_id = attr_map.get("id")
        if element_id:
            self.elements[element_id] = {"tag": tag, "attrs": attr_map, "text": []}

    def handle_endtag(self, tag):
        if self._stack:
            self._stack.pop()

    def handle_data(self, data):
        for element_id in reversed(self._stack):
            if element_id and element_id in self.elements:
                self.elements[element_id]["text"].append(data)
                break

    def text(self, element_id: str) -> str:
        entry = self.elements[element_id]
        return "".join(entry["text"]).strip()

    def attrs(self, element_id: str) -> dict[str, object]:
        return dict(self.elements[element_id]["attrs"])


def _parse(html: str) -> _IdParser:
    parser = _IdParser()
    parser.feed(html)
    return parser


def _create(client, **overrides):
    payload = {
        "name": "screenshot-page",
        "host": "STREAM-HOST",
        "client": "couch",
        "network_path": "local-LAN",
    }
    payload.update(overrides)
    response = client.post("/api/sessions", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _auth() -> dict[str, str]:
    return {"X-Frame-Relay-Screenshot-Token": config.SCREENSHOT_TOKEN}


def _complete_request(client, sid: str, request_id: int, source: str, machine: str, captured_at: str, display_name: str):
    response = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data={
            "source": source,
            "machine": machine,
            "captured_at": captured_at,
            "display_name": display_name,
        },
        files={"file": ("capture.png", PNG_BYTES, "image/png")},
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_screenshot_comparison_page_renders_images_statuses_and_keeps_token_client_side(client):
    session = _create(client, name="page-comparison")
    sid = session["id"]

    first = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host", "client"]},
        headers=_auth(),
    )
    assert first.status_code == 200, first.text
    host_request, client_request = first.json()

    host_completed = _complete_request(
        client,
        sid,
        host_request["id"],
        "host",
        "HostCaptureRig",
        "2026-08-13T12:00:00Z",
        "LG C2",
    )
    client_completed = _complete_request(
        client,
        sid,
        client_request["id"],
        "client",
        "ClientCaptureRig",
        "2026-08-13T12:00:05Z",
        "Steam Deck OLED",
    )

    host_pending = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    assert host_pending.status_code == 200, host_pending.text

    client_failed = client.post(
        f"/api/sessions/{sid}/screenshot-requests",
        json={"targets": ["client"]},
        headers=_auth(),
    )
    assert client_failed.status_code == 200, client_failed.text
    failed_request_id = client_failed.json()[0]["id"]
    failed = client.post(
        f"/api/sessions/{sid}/screenshot-requests/{failed_request_id}/fail",
        json={"source": "client", "error": "<capture> & blocked", "machine": "Xbox"},
        headers=_auth(),
    )
    assert failed.status_code == 200, failed.text

    page = client.get(f"/sessions/{sid}")
    assert page.status_code == 200, page.text
    assert "Host/client screenshot comparison" in page.text
    assert "Collectors on both machines must share the same screenshot token." in page.text
    assert "not frame synchronized" in page.text
    assert "protected content can come back black" in page.text
    assert "Xbox/manual-entry clients cannot" in page.text
    assert "fulfill client screenshot requests." in page.text
    assert config.SCREENSHOT_TOKEN not in page.text
    assert "<capture> & blocked" not in page.text
    assert "&lt;capture&gt; &amp; blocked" in page.text

    parser = _parse(page.text)
    token_attrs = parser.attrs("screenshot-token")
    assert token_attrs["type"] == "password"
    assert "value" not in token_attrs
    assert "disabled" not in token_attrs
    assert "disabled" not in parser.attrs("screenshot-request-both")
    assert "disabled" not in parser.attrs("screenshot-request-host")
    assert "disabled" not in parser.attrs("screenshot-request-client")

    assert parser.attrs("screenshot-host-image")["src"] == f"/artifacts/{host_completed['artifact_filename']}"
    assert parser.attrs("screenshot-client-image")["src"] == f"/artifacts/{client_completed['artifact_filename']}"
    assert parser.text("screenshot-host-caption") == host_completed["artifact_caption"]
    assert parser.text("screenshot-client-caption") == client_completed["artifact_caption"]
    assert parser.text("screenshot-host-machine") == "HostCaptureRig"
    assert parser.text("screenshot-client-machine") == "ClientCaptureRig"
    assert parser.text("screenshot-host-completed") == "2026-08-13T12:00:00Z"
    assert parser.text("screenshot-client-completed") == "2026-08-13T12:00:05Z"
    assert parser.text("screenshot-host-state") == "pending"
    assert parser.text("screenshot-client-state") == "failed"
    assert parser.text("screenshot-host-summary").startswith("pending · requested ")
    assert parser.text("screenshot-client-summary").startswith("failed · ")
    assert parser.text("screenshot-client-error") == "<capture> & blocked"


def test_screenshot_comparison_page_disables_request_controls_when_session_stops(client):
    session = _create(client, name="stopped-page")
    stopped = client.post(f"/api/sessions/{session['id']}/stop")
    assert stopped.status_code == 200, stopped.text

    page = client.get(f"/sessions/{session['id']}")
    assert page.status_code == 200, page.text
    assert "Host/client screenshot comparison" in page.text
    assert "Session stopped — new screenshot requests are disabled." in page.text

    parser = _parse(page.text)
    assert "disabled" in parser.attrs("screenshot-token")
    assert "disabled" in parser.attrs("screenshot-request-both")
    assert "disabled" in parser.attrs("screenshot-request-host")
    assert "disabled" in parser.attrs("screenshot-request-client")


def test_session_bundle_includes_screenshot_request_fields_used_by_live_refresh(client):
    session = _create(client, name="bundle-shape")
    queued = client.post(
        f"/api/sessions/{session['id']}/screenshot-requests",
        json={"targets": ["host"]},
        headers=_auth(),
    )
    assert queued.status_code == 200, queued.text

    bundle = client.get(f"/api/sessions/{session['id']}")
    assert bundle.status_code == 200, bundle.text
    request = bundle.json()["screenshot_requests"][0]
    assert {
        "target_source",
        "status",
        "requested_at",
        "completed_at",
        "machine",
        "error",
        "artifact_filename",
        "artifact_caption",
    } <= request.keys()
