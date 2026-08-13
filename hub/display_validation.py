"""Evaluate Windows display-topology samples against a session's stream settings."""
from __future__ import annotations

from typing import Any


def _resolution(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str) or "x" not in value.lower():
        return None
    left, right = value.lower().split("x", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None


def _phase(samples: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    rows = [sample for sample in samples if sample.get("phase") == phase]
    timestamps = [sample.get("sampled_at") for sample in rows if sample.get("sampled_at")]
    if not timestamps:
        return rows
    latest = max(timestamps)
    return [sample for sample in rows if sample.get("sampled_at") == latest]


def _identity(sample: dict[str, Any]) -> tuple[Any, ...]:
    return (
        sample.get("adapter_id"),
        sample.get("target_id"),
        sample.get("device_path"),
    )


def _candidate(samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    virtual = [sample for sample in samples if sample.get("is_virtual") in (True, 1)]
    pool = virtual or [sample for sample in samples if sample.get("primary") in (True, 1)]
    return pool[0] if pool else (samples[0] if len(samples) == 1 else None)


def summarize(session: dict[str, Any],
              samples: list[dict[str, Any]]) -> dict[str, Any]:
    samples = [sample for sample in samples if sample.get("source") == "host"]
    before = _phase(samples, "before")
    during = _phase(samples, "during")
    after = _phase(samples, "after")
    candidate = _candidate(during)
    requested = session.get("requested_settings") or {}

    virtual_values = {
        bool(sample.get("is_virtual"))
        for sample in during
        if sample.get("is_virtual") is not None
    }
    virtual_active = True if True in virtual_values else (
        False if virtual_values == {False} else None
    )

    expected_resolution = _resolution(session.get("resolution"))
    if expected_resolution is None:
        expected_resolution = _resolution(requested.get("resolution"))
    actual_resolution = None
    if candidate and candidate.get("width") is not None and candidate.get("height") is not None:
        actual_resolution = (candidate["width"], candidate["height"])
    resolution_matches = (
        actual_resolution == expected_resolution
        if actual_resolution is not None and expected_resolution is not None else None
    )

    expected_fps = session.get("fps")
    if expected_fps is None:
        expected_fps = requested.get("fps")
    actual_refresh = candidate.get("refresh_hz") if candidate else None
    refresh_matches = None
    if expected_fps is not None and actual_refresh is not None:
        refresh_matches = abs(float(actual_refresh) - float(expected_fps)) <= 1.0

    expected_hdr = requested.get("hdr")
    if expected_hdr is None and session.get("hdr"):
        expected_hdr = True
    actual_hdr = candidate.get("hdr_enabled") if candidate else None
    hdr_matches = (
        bool(actual_hdr) == bool(expected_hdr)
        if expected_hdr is not None and actual_hdr is not None else None
    )

    restored_after = None
    if before and after:
        restored_after = {_identity(sample) for sample in before} == {
            _identity(sample) for sample in after
        }

    checks = {
        "topology_observed": bool(during),
        "virtual_display_active": virtual_active,
        "resolution_matches": resolution_matches,
        "refresh_matches": refresh_matches,
        "hdr_matches": hdr_matches,
        "only_active_display": len(during) == 1 if during else None,
        "topology_restored_after": restored_after,
    }
    required = [
        "topology_observed",
        "virtual_display_active",
        "resolution_matches",
        "refresh_matches",
        "hdr_matches",
    ]
    if session.get("status") == "stopped":
        required.append("topology_restored_after")
    known_required = [checks[name] for name in required if checks[name] is not None]
    if not during:
        status = "partial"
    elif any(value is False for value in known_required):
        status = "fail"
    elif all(checks.get(name) is True for name in required):
        status = "pass"
    else:
        status = "partial"

    name = None
    if candidate:
        name = candidate.get("friendly_name") or candidate.get("source_name")
    return {
        "status": status,
        "display_name": name,
        "candidate": candidate,
        "checks": checks,
        "expected": {
            "resolution": (
                f"{expected_resolution[0]}x{expected_resolution[1]}"
                if expected_resolution else None
            ),
            "refresh_hz": expected_fps,
            "hdr": expected_hdr,
        },
        "actual": {
            "resolution": (
                f"{actual_resolution[0]}x{actual_resolution[1]}"
                if actual_resolution else None
            ),
            "refresh_hz": actual_refresh,
            "hdr": actual_hdr,
        },
    }
