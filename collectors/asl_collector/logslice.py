"""Extract the log slice that belongs to a capture window.

Two strategies, most-reliable first:
1. byte offset - record the file size when a session starts, then read only the bytes
   appended by the time it stops. Works for any log (even Moonlight-Qt lines that use a
   relative, not wall-clock, timestamp).
2. wall-clock slice - for logs whose lines carry a timestamp (Apollo/Sunshine), keep the
   lines between start and stop. Falls back to a tail of the file when no timestamps parse.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

# Wall-clock timestamp patterns seen at the start of a log line.
_TS_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})"), "ymd"),
    (re.compile(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2}):(\d{2})"), "ymd"),
    (re.compile(r"(\d{4}):(\d{2}):(\d{2}):(\d{2}):(\d{2}):(\d{2})"), "ymd"),
]


def file_offset(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def read_since(path: str, offset: int) -> str:
    """Read bytes appended after ``offset``. If the file shrank (rotated), read it all."""
    return read_new(path, offset)[0]


def read_new(path: str, offset: int) -> tuple[str, int]:
    """Read text appended after ``offset`` and report the new offset.

    Returns ``(text, next_offset)`` where ``next_offset`` is where the next incremental read
    should resume (so callers can post logs live in chunks without duplicating or skipping
    lines). If the file shrank (rotated), it is read from the start.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", offset
    start = offset if offset <= size else 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(start)
        text = fh.read()
        return text, fh.tell()


def extract_timestamp(line: str) -> Optional[datetime]:
    for pat, _ in _TS_PATTERNS:
        m = pat.search(line)
        if m:
            try:
                y, mo, d, h, mi, s = (int(g) for g in m.groups())
                return datetime(y, mo, d, h, mi, s)
            except ValueError:
                return None
    return None


def slice_by_time(text: str, start: datetime, stop: datetime) -> Optional[str]:
    """Keep lines whose timestamp is within [start, stop]. None if nothing has a timestamp."""
    kept: list[str] = []
    last: Optional[datetime] = None
    saw_ts = False
    for line in text.splitlines():
        ts = extract_timestamp(line)
        if ts is not None:
            saw_ts = True
            last = ts
        current = last
        if current is not None and start <= current <= stop:
            kept.append(line)
    if not saw_ts:
        return None
    return "\n".join(kept)


def tail(text: str, n: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def slice_file(path: str, start: datetime, stop: datetime, tail_lines: int = 2000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    sliced = slice_by_time(text, start, stop)
    if sliced:
        return sliced
    return tail(text, tail_lines)
