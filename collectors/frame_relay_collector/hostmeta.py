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
from typing import Any, Iterable, Optional


def _last(pattern: str, text: str, flags: int = 0) -> Optional[re.Match]:
    m = None
    for m in re.finditer(pattern, text, flags):
        pass
    return m


def _last_any(patterns: Iterable[str], text: str, flags: int = 0) -> Optional[re.Match]:
    found = None
    pos = -1
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags):
            if match.start() >= pos:
                found = match
                pos = match.start()
    return found


def _clean_value(value: str) -> str:
    return value.strip().strip("\"'[] ")


def _parse_bool_token(token: str) -> Optional[bool]:
    value = token.strip().lower()
    if value in {"1", "true", "yes", "on", "hdr"}:
        return True
    if value in {"0", "false", "no", "off", "sdr"}:
        return False
    return None


def _parse_dynamic_range(token: str) -> int | str:
    value = _clean_value(token)
    return int(value) if value.isdigit() else value


def _parse_kbps(token: str) -> int:
    return round(int(token) / 1000)


def _apply_color_coding(raw: str, hdr_details: dict[str, Any]) -> None:
    value = raw.strip().strip("\"'[] ")
    if not value:
        return
    hdr_details.setdefault("evidence", []).append(f"Apollo log: Color coding: {value}")
    m = re.search(r"\b(HDR|SDR)\b", value, re.IGNORECASE)
    if m:
        hdr_details["encoded_hdr"] = m.group(1).upper() == "HDR"
    primaries = re.search(r"\b(Rec\.?\s*2020|BT\.?\s*2020|Rec\.?\s*709|BT\.?\s*709|DCI-?P3|Display P3)\b",
                          value, re.IGNORECASE)
    if primaries:
        hdr_details["color_primaries"] = primaries.group(1)
    transfer = re.search(r"\b(SMPTE\s*2084\s*PQ|PQ|HLG|Gamma\s*2\.[24]|sRGB)\b",
                         value, re.IGNORECASE)
    if transfer:
        hdr_details["transfer_function"] = transfer.group(1)
    depth = re.search(r"(\d+)\s*(?:-\s*)?bit\b", value, re.IGNORECASE)
    if depth:
        hdr_details["bit_depth"] = int(depth.group(1))


def _parse_named_line(line: str, markers: Iterable[str]) -> Optional[str]:
    low = line.lower()
    positions = [low.find(marker) for marker in markers if marker in low]
    if not positions:
        return None
    segment = line[min(positions):]
    for pattern in (r"\[([^\]]+)\]", r'"([^"]+)"'):
        for candidate in re.findall(pattern, segment):
            value = _clean_value(candidate)
            if value and not value.isdigit():
                return value
    m = re.search(r":\s*(.+)$", segment)
    if not m:
        return None
    value = _clean_value(re.split(r"\s+(?:app(?:lication)?\s+)?id\s*[:=]", m.group(1), maxsplit=1,
                                   flags=re.IGNORECASE)[0])
    return value or None


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
    """Best-effort extraction of effective + observed Apollo metadata from a log slice."""
    out: dict[str, Any] = {}
    requested_settings: dict[str, Any] = {}
    hdr_details: dict[str, Any] = {}

    apollo_app = None
    game_title = None
    for line in text.splitlines():
        low = line.lower()
        if "applications for" not in low:
            app = _parse_named_line(
                line,
                ("selected application", "launching application", "launch application",
                 "selected app", "launching app"),
            )
            if app:
                apollo_app = app
        title = _parse_named_line(
            line,
            ("game title", "process title", "game name", "process name"),
        )
        if title:
            game_title = title
    if apollo_app:
        out["apollo_app"] = apollo_app
    if game_title:
        out["game_title"] = game_title

    m = _last(r"Requested frame rate \[(\d+)\s*fps\]", text)
    if m:
        out["fps"] = int(m.group(1))
        requested_settings["fps"] = int(m.group(1))

    m = _last(r"Desktop resolution \[(\d+x\d+)\]", text)
    if m:
        out["resolution"] = m.group(1)

    # Host streaming bitrate is authoritative; fall back to the client request.
    m = _last(r"Host Streaming bitrate is \[(\d+)\s*kbps\]", text) \
        or _last(r"Client Requested bitrate is \[(\d+)\s*kbps\]", text)
    if m:
        out["bitrate_mbps"] = _parse_kbps(m.group(1))

    m = _last(r"Display is HDR:\s*(true|false)", text, re.IGNORECASE)
    if m:
        out["hdr"] = m.group(1).lower() == "true"
        hdr_details["host_display_hdr"] = out["hdr"]
        hdr_details.setdefault("evidence", []).append(
            f"Apollo log: Display is HDR: {str(out['hdr']).lower()}"
        )

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

    m = _last_any((
        r"Client Requested (?:video )?codec(?: is)? \[([^\]]+)\]",
        r"Requested codec(?: is)? \[([^\]]+)\]",
        r"Client requested codec(?: is)?[:=]\s*([^\r\n]+)$",
    ), text, re.IGNORECASE | re.MULTILINE)
    if m:
        requested_codec = normalize_codec(_clean_value(next(g for g in m.groups() if g)))
        if requested_codec:
            requested_settings["codec"] = requested_codec

    m = _last_any((
        r"Client Requested (?:desktop |stream )?resolution(?: is)? \[(\d+x\d+)\]",
        r"Requested (?:desktop |stream )?resolution(?: is)? \[(\d+x\d+)\]",
        r"Client requested resolution(?: is)?[:=]\s*(\d+x\d+)\b",
    ), text, re.IGNORECASE)
    if m:
        requested_settings["resolution"] = _clean_value(m.group(1))

    m = _last_any((
        r"Client Requested bitrate is \[(\d+)\s*kbps\]",
        r"Requested bitrate(?: is)? \[(\d+)\s*kbps\]",
        r"Client requested bitrate(?: is)?[:=]\s*(\d+)\s*kbps\b",
    ), text, re.IGNORECASE)
    if m:
        requested_settings["bitrate_mbps"] = _parse_kbps(m.group(1))

    requested_hdr = None
    m = _last_any((
        r"Client Requested HDR(?: is)? \[(true|false|1|0)\]",
        r"Requested HDR(?: is)? \[(true|false|1|0)\]",
        r"Client requested HDR(?: is)?[:=]\s*(true|false|1|0)\b",
    ), text, re.IGNORECASE)
    if m:
        requested_hdr = _parse_bool_token(m.group(1))

    m = _last(r"Client dynamicRange:\s*([^,\r\n]+)", text, re.IGNORECASE)
    if m:
        dynamic_range = _parse_dynamic_range(m.group(1))
        if requested_hdr is None:
            requested_hdr = _parse_bool_token(str(dynamic_range))
    if requested_hdr is not None:
        requested_settings["hdr"] = requested_hdr
        hdr_details["requested"] = requested_hdr

    m = _last(r"Color coding:\s*([^\r\n]+)", text, re.IGNORECASE)
    if m:
        _apply_color_coding(m.group(1), hdr_details)

    if requested_settings:
        out["requested_settings"] = requested_settings
    if hdr_details:
        hdr_details["confidence"] = 0.9
        out["hdr_details"] = hdr_details

    return out
