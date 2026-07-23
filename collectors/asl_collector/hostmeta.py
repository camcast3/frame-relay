"""Derive session metadata from an Apollo/Sunshine host log slice.

Apollo logs the negotiated stream parameters at session start, e.g.::

    Info: Requested frame rate [60fps]
    Info: Desktop resolution [2560x1600]
    Info: Host Streaming bitrate is [44000kbps]
    Info: Client dynamicRange: 0, Display is HDR: false
    Info: Found H.264 encoder: libx264 [software]   (or: Creating encoder [hevc_amf])

The client IP/name and therefore the network path are NOT in the log, so those remain
manual. We take the last match of each field (the most recent negotiation wins).
"""
from __future__ import annotations

import re
from typing import Any, Optional


def _last(pattern: str, text: str, flags: int = 0) -> Optional[re.Match]:
    m = None
    for m in re.finditer(pattern, text, flags):
        pass
    return m


def normalize_codec(token: str) -> Optional[str]:
    t = token.lower()
    if "av1" in t:
        return "AV1"
    if "hevc" in t or "265" in t:
        return "HEVC"
    if "264" in t:
        return "H.264"
    return None


def parse_apollo_metadata(text: str) -> dict[str, Any]:
    """Best-effort extraction of {codec, resolution, fps, bitrate_mbps, hdr} from a log slice."""
    out: dict[str, Any] = {}

    m = _last(r"Requested frame rate \[(\d+)\s*fps\]", text)
    if m:
        out["fps"] = int(m.group(1))

    m = _last(r"Desktop resolution \[(\d+x\d+)\]", text)
    if m:
        out["resolution"] = m.group(1)

    # Host streaming bitrate is authoritative; fall back to the client request.
    m = _last(r"Host Streaming bitrate is \[(\d+)\s*kbps\]", text) \
        or _last(r"Client Requested bitrate is \[(\d+)\s*kbps\]", text)
    if m:
        out["bitrate_mbps"] = round(int(m.group(1)) / 1000)

    m = _last(r"Display is HDR:\s*(true|false)", text, re.IGNORECASE)
    if m:
        out["hdr"] = m.group(1).lower() == "true"

    # Prefer the chosen encoder ("Found <codec> encoder"), else the last "Creating encoder [x]".
    codec = None
    m = _last(r"Found\s+(H\.?26[45]|HEVC|AV1)\s+encoder", text, re.IGNORECASE)
    if m:
        codec = normalize_codec(m.group(1))
    if not codec:
        m = _last(r"Creating encoder \[([^\]]+)\]", text)
        if m:
            codec = normalize_codec(m.group(1))
    if codec:
        out["codec"] = codec

    return out
