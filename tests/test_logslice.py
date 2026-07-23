"""Unit tests for log slicing (byte-offset capture + wall-clock slice + tail fallback)."""
from datetime import datetime

from asl_collector import logslice
from conftest import SAMPLES


def test_extract_timestamp_variants():
    assert logslice.extract_timestamp("[2026-07-23 10:00:01]: Info: x") == datetime(2026, 7, 23, 10, 0, 1)
    assert logslice.extract_timestamp("2026/07/23 10:00:02 hello") == datetime(2026, 7, 23, 10, 0, 2)
    assert logslice.extract_timestamp("no timestamp here") is None


def test_slice_by_time_keeps_window():
    text = (SAMPLES / "apollo-sunshine.log").read_text()
    out = logslice.slice_by_time(text, datetime(2026, 7, 23, 10, 0, 0), datetime(2026, 7, 23, 10, 0, 20))
    assert "CLIENT CONNECTED" in out
    assert "encoder busy" in out
    assert "Sunshine version" not in out    # 09:59:58, before the window
    assert "CLIENT DISCONNECTED" not in out  # 10:00:40, after the window


def test_slice_by_time_none_when_no_timestamps():
    assert logslice.slice_by_time("line one\nline two\n", datetime(2026, 1, 1), datetime(2030, 1, 1)) is None


def test_tail():
    assert logslice.tail("a\nb\nc\nd", 2) == "c\nd"


def test_offset_and_read_since(tmp_path):
    p = tmp_path / "app.log"
    p.write_text("first\n")
    off = logslice.file_offset(str(p))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("second\nthird\n")
    appended = logslice.read_since(str(p), off)
    assert "first" not in appended
    assert "second" in appended and "third" in appended


def test_read_since_handles_rotation(tmp_path):
    p = tmp_path / "app.log"
    p.write_text("a\nb\nc\nd\ne\n")
    off = logslice.file_offset(str(p))
    p.write_text("x\n")  # rotated/shrunk: offset now past EOF -> read whole file
    assert logslice.read_since(str(p), off) == "x\n"


def test_slice_file_tail_fallback(tmp_path):
    p = tmp_path / "notimestamps.log"
    p.write_text("\n".join(f"line{i}" for i in range(5000)))
    out = logslice.slice_file(str(p), datetime(2026, 1, 1), datetime(2030, 1, 1), tail_lines=100)
    assert len(out.splitlines()) == 100
    assert "line4999" in out
