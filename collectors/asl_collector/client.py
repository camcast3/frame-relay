"""Minimal hub API client - standard library only (urllib), no third-party deps."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Optional


class HubError(RuntimeError):
    pass


def _request(
    method: str,
    url: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    data: bytes | None = None,
    headers: Optional[dict[str, str]] = None,
) -> Any:
    if payload is not None and data is not None:
        raise ValueError("payload and data are mutually exclusive")
    body = data
    merged_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode()
        merged_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=merged_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:  # noqa: PERF203
        raise HubError(f"{method} {url} -> {e.code}: {e.read().decode(errors='replace')}") from e
    except urllib.error.URLError as e:
        raise HubError(f"{method} {url} -> {e.reason}") from e


def create_session(hub: str, payload: dict[str, Any]) -> str:
    res = _request("POST", f"{hub}/api/sessions", payload)
    return res["id"]


def list_sessions(hub: str, awaiting_client: bool = False,
                  awaiting_host: bool = False) -> list[dict[str, Any]]:
    url = f"{hub}/api/sessions"
    params = []
    if awaiting_client:
        params.append("awaiting_client=true")
    if awaiting_host:
        params.append("awaiting_host=true")
    if params:
        url += "?" + "&".join(params)
    return _request("GET", url) or []


def get_session(hub: str, sid: str) -> Optional[dict[str, Any]]:
    res = _request("GET", f"{hub}/api/sessions/{sid}")
    return res.get("session") if res else None


def patch_session(hub: str, sid: str, fields: dict[str, Any]) -> None:
    _request("PATCH", f"{hub}/api/sessions/{sid}", fields)


def post_log(hub: str, sid: str, source: str, role: str, content: str,
             machine: Optional[str] = None, meta: Optional[dict[str, Any]] = None) -> None:
    payload = {"source": source, "role": role, "content": content, "machine": machine}
    if meta:
        payload["meta"] = meta
    _request("POST", f"{hub}/api/sessions/{sid}/logs", payload)


def post_observations(hub: str, sid: str, payload: dict[str, Any]) -> None:
    _request("POST", f"{hub}/api/sessions/{sid}/observations", payload)


def post_links(hub: str, sid: str, samples: list[dict[str, Any]]) -> int:
    res = _request("POST", f"{hub}/api/sessions/{sid}/links", {"samples": samples})
    return res.get("added", 0)


def post_displays(hub: str, sid: str, samples: list[dict[str, Any]]) -> int:
    res = _request("POST", f"{hub}/api/sessions/{sid}/displays", {"samples": samples}) or {}
    return res.get("added", len(samples))


def post_nettest(hub: str, sid: str, result: dict[str, Any]) -> None:
    _request("POST", f"{hub}/api/sessions/{sid}/nettests", result)


def stop_session(hub: str, sid: str) -> None:
    _request("POST", f"{hub}/api/sessions/{sid}/stop")


def _screenshot_headers(token: str | None) -> dict[str, str]:
    token = (token or "").strip()
    return {"X-ASL-Screenshot-Token": token} if token else {}


def _encode_multipart(
    fields: dict[str, object | None],
    *,
    file_field: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"----aslcollector{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        if value is None:
            continue
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    parts.extend([
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\n'
        ).encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(parts), boundary


def pending_screenshot_requests(
    hub: str,
    sid: str,
    source: str,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"source": source})
    url = f"{hub}/api/sessions/{sid}/screenshot-requests/pending?{params}"
    return _request("GET", url, headers=_screenshot_headers(token)) or []


def complete_screenshot_request(
    hub: str,
    sid: str,
    request_id: int,
    source: str,
    path: str,
    *,
    machine: str | None = None,
    captured_at: str | None = None,
    display_name: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    with open(path, "rb") as fh:
        content = fh.read()
    body, boundary = _encode_multipart(
        {
            "source": source,
            "machine": machine,
            "captured_at": captured_at,
            "display_name": display_name,
        },
        file_field="file",
        filename=os.path.basename(path) or "capture.png",
        content=content,
        content_type="image/png",
    )
    headers = _screenshot_headers(token)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    return _request(
        "POST",
        f"{hub}/api/sessions/{sid}/screenshot-requests/{request_id}/complete",
        data=body,
        headers=headers,
    )


def fail_screenshot_request(
    hub: str,
    sid: str,
    request_id: int,
    source: str,
    error: str,
    *,
    machine: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    return _request(
        "POST",
        f"{hub}/api/sessions/{sid}/screenshot-requests/{request_id}/fail",
        {"source": source, "error": error, "machine": machine},
        headers=_screenshot_headers(token),
    )
