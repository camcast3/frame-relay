"""Minimal hub API client - standard library only (urllib), no third-party deps."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


class HubError(RuntimeError):
    pass


def _request(method: str, url: str, payload: Optional[dict[str, Any]] = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                headers={"Content-Type": "application/json"})
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


def list_sessions(hub: str, awaiting_client: bool = False) -> list[dict[str, Any]]:
    url = f"{hub}/api/sessions"
    if awaiting_client:
        url += "?awaiting_client=true"
    return _request("GET", url) or []


def get_session(hub: str, sid: str) -> Optional[dict[str, Any]]:
    res = _request("GET", f"{hub}/api/sessions/{sid}")
    return res.get("session") if res else None


def patch_session(hub: str, sid: str, fields: dict[str, Any]) -> None:
    _request("PATCH", f"{hub}/api/sessions/{sid}", fields)


def post_log(hub: str, sid: str, source: str, role: str, content: str,
             machine: Optional[str] = None) -> None:
    _request("POST", f"{hub}/api/sessions/{sid}/logs",
             {"source": source, "role": role, "content": content, "machine": machine})


def post_links(hub: str, sid: str, samples: list[dict[str, Any]]) -> int:
    res = _request("POST", f"{hub}/api/sessions/{sid}/links", {"samples": samples})
    return res.get("added", 0)


def post_nettest(hub: str, sid: str, result: dict[str, Any]) -> None:
    _request("POST", f"{hub}/api/sessions/{sid}/nettests", result)


def stop_session(hub: str, sid: str) -> None:
    _request("POST", f"{hub}/api/sessions/{sid}/stop")
