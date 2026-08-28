"""Derive observed client metadata from Moonlight/Artemis log text."""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from .hostmeta import normalize_codec


def _last(pattern: str, text: str, flags: int = 0) -> Optional[re.Match]:
    match = None
    for match in re.finditer(pattern, text, flags):
        pass
    return match


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
    hdr_details.setdefault("evidence", []).append(f"Client log: Color coding: {value}")
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


def _parse_version(text: str, role: str) -> Optional[str]:
    role_patterns = {
        "moonlight": (
            r"\bMoonlight(?:-Qt)?(?:\s+version)?[: ]\s*v?([0-9]+(?:\.[0-9A-Za-z]+)+(?:[-+][0-9A-Za-z.]+)?)\b",
            r"\bversion[: ]\s*v?([0-9]+(?:\.[0-9A-Za-z]+)+(?:[-+][0-9A-Za-z.]+)?)\b.*\bMoonlight\b",
        ),
        "artemis": (
            r"\bArtemis(?:\s+Game Streaming)?(?:\s+version)?[: ]\s*v?([0-9]+(?:\.[0-9A-Za-z]+)+(?:[-+][0-9A-Za-z.]+)?)\b",
            r"\bversion[: ]\s*v?([0-9]+(?:\.[0-9A-Za-z]+)+(?:[-+][0-9A-Za-z.]+)?)\b.*\bArtemis\b",
        ),
    }
    patterns = role_patterns.get(role, ())
    match = _last_any(patterns, text, re.IGNORECASE)
    return _clean_value(match.group(1)) if match else None


def parse_client_metadata(text: str, role: str) -> dict[str, Any]:
    """Best-effort extraction of observed client metadata from Moonlight/Artemis logs."""
    out: dict[str, Any] = {}
    requested_settings: dict[str, Any] = {}
    hdr_details: dict[str, Any] = {}

    version = _parse_version(text, role)
    if version:
        out["client_version"] = version

    width = None
    height = None
    resolution = _last(r"\b(?:resolution|stream size)[:=]\s*(\d+)\s*[xX]\s*(\d+)\b", text,
                       re.IGNORECASE)
    if resolution:
        width, height = resolution.group(1), resolution.group(2)
    m = _last_any((
        r"Setting stream width to (\d+)\b",
        r"\bwidth=(\d+)\b",
        r"\bstream width[:=]\s*(\d+)\b",
    ), text, re.IGNORECASE)
    if m:
        width = m.group(1)
    m = _last_any((
        r"Setting stream height to (\d+)\b",
        r"\bheight=(\d+)\b",
        r"\bstream height[:=]\s*(\d+)\b",
    ), text, re.IGNORECASE)
    if m:
        height = m.group(1)
    if width and height:
        requested_settings["resolution"] = f"{int(width)}x{int(height)}"

    m = _last_any((
        r"Setting (?:stream )?frame rate to (\d+)\s*(?:fps|FPS)\b",
        r"\b(?:requested )?fps(?:=|:\s*)(\d+)\b",
        r"\bframe rate(?:=|:\s*)(\d+)\b",
    ), text, re.IGNORECASE)
    if m:
        requested_settings["fps"] = int(m.group(1))

    m = _last_any((
        r"Setting bitrate to (\d+)\s*kbps\b",
        r"\bbitrate(?:=|:\s*)(\d+)\b",
        r"\bbitrate target(?:=|:\s*)(\d+)\s*kbps\b",
    ), text, re.IGNORECASE)
    if m:
        requested_settings["bitrate_mbps"] = _parse_kbps(m.group(1))

    m = _last_any((
        r"Requested (?:video )?codec:\s*([A-Za-z0-9_.-]+)\b",
        r"Initial video codec:\s*([A-Za-z0-9_.-]+)\b",
        r"\bcodec=([A-Za-z0-9_.-]+)\b",
    ), text, re.IGNORECASE)
    if m:
        codec = normalize_codec(m.group(1))
        if codec:
            requested_settings["codec"] = codec

    requested_hdr = None
    m = _last(r"\bhdrMode(?:=|:\s*)([A-Za-z0-9_.-]+)\b", text, re.IGNORECASE)
    if m:
        hdr_mode = _parse_dynamic_range(m.group(1))
        requested_hdr = _parse_bool_token(str(hdr_mode))
    m = _last_any((
        r"\bdynamicRange(?:=|:\s*)([A-Za-z0-9_.-]+)\b",
        r"\bdynamic range(?:=|:\s*)([A-Za-z0-9_.-]+)\b",
    ), text, re.IGNORECASE)
    if m:
        dynamic_range = _parse_dynamic_range(m.group(1))
        if requested_hdr is None:
            requested_hdr = _parse_bool_token(str(dynamic_range))
    if requested_hdr is not None:
        requested_settings["hdr"] = requested_hdr
        hdr_details["requested"] = requested_hdr

    m = _last_any((
        r"Display (?:is )?HDR(?: mode)?:\s*(true|false|on|off|yes|no)\b",
        r"\bdisplayHdr(?:=|:\s*)(true|false|1|0)\b",
    ), text, re.IGNORECASE)
    if m:
        display_hdr = _parse_bool_token(m.group(1))
        if display_hdr is not None:
            hdr_details["client_display_hdr"] = display_hdr

    m = _last_any((
        r"(?:Chosen|Using|Selected) renderer:\s*([^\r\n]+)",
        r"\brenderer(?:=|:\s*)([^\r\n]+)",
        r"Decoder renderer:\s*([^\r\n]+)",
    ), text, re.IGNORECASE)
    if m:
        hdr_details["client_renderer"] = _clean_value(m.group(1))

    m = _last_any((
        r"([A-Za-z0-9 .+/_()-]+?)\s+video decoder chosen\b",
        r"(?:Chosen|Using|Selected) decoder:\s*([^\r\n]+)",
        r"\bdecoder(?:=|:\s*)([^\r\n]+)",
    ), text, re.IGNORECASE)
    if m:
        value = next(group for group in m.groups() if group)
        hdr_details["client_decoder"] = _clean_value(value)

    m = _last_any((
        r"Color coding:\s*([^\r\n]+)",
        r"\bcolorCoding(?:=|:\s*)([^\r\n]+)",
    ), text, re.IGNORECASE)
    if m:
        _apply_color_coding(m.group(1), hdr_details)

    m = _last(r"(?:Color )?primaries(?:=|:\s*)([^\r\n]+)", text, re.IGNORECASE)
    if m:
        hdr_details["color_primaries"] = _clean_value(m.group(1))

    m = _last(r"(?:Transfer|Transfer function|EOTF)(?:=|:\s*)([^\r\n]+)", text, re.IGNORECASE)
    if m:
        hdr_details["transfer_function"] = _clean_value(m.group(1))

    m = _last(r"bit depth(?:=|:\s*)(\d+)\s*(?:bit|-bit)?", text, re.IGNORECASE)
    if m:
        hdr_details["bit_depth"] = int(m.group(1))

    m = _last_any((
        r"tone mapping(?:=|:\s*)([^\r\n]+)",
        r"\btonemapping(?:=|:\s*)([^\r\n]+)",
    ), text, re.IGNORECASE)
    if m:
        hdr_details["tone_mapping"] = _clean_value(m.group(1))

    for line in text.splitlines():
        low = line.lower()
        if "hdr" not in low:
            continue
        if "fallback" in low or "fall back" in low:
            hdr_details["status"] = "fallback"
            hdr_details.setdefault("evidence", []).append(line.strip())
        elif any(token in low for token in ("warning", "disabled", "unsupported")):
            hdr_details.setdefault("evidence", []).append(line.strip())
            if requested_hdr is True:
                hdr_details["status"] = "failed"

    if requested_hdr is True and "status" not in hdr_details:
        if hdr_details.get("encoded_hdr") is False or hdr_details.get("client_display_hdr") is False:
            hdr_details["status"] = "fallback"
        elif (hdr_details.get("encoded_hdr") is True
              and hdr_details.get("client_display_hdr") is True):
            hdr_details["status"] = "working"

    if requested_settings:
        out["requested_settings"] = requested_settings
    if hdr_details:
        hdr_details["confidence"] = 0.9
        out["hdr_details"] = hdr_details
    return out
