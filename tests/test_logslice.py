"""Unit tests for log slicing (byte-offset capture + wall-clock slice + tail fallback)."""
from datetime import datetime, timezone

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


def test_slice_by_time_accepts_aware_bounds():
    """Callers work in aware UTC; log lines are naive *local* wall clock.

    Comparing them raw raises TypeError, and stripping the zone without converting would shift
    the window by the UTC offset - so an aware bound must select the same lines as the naive
    local instant it represents.
    """
    text = (SAMPLES / "apollo-sunshine.log").read_text()
    naive_start = datetime(2026, 7, 23, 10, 0, 0)
    naive_stop = datetime(2026, 7, 23, 10, 0, 20)
    expected = logslice.slice_by_time(text, naive_start, naive_stop)

    local_tz = datetime.now().astimezone().tzinfo
    aware_start = naive_start.replace(tzinfo=local_tz).astimezone(timezone.utc)
    aware_stop = naive_stop.replace(tzinfo=local_tz).astimezone(timezone.utc)

    got = logslice.slice_by_time(text, aware_start, aware_stop)
    assert got == expected
    assert "CLIENT CONNECTED" in got
    assert "CLIENT DISCONNECTED" not in got


def test_slice_file_accepts_aware_bounds(tmp_path):
    log = tmp_path / "sunshine.log"
    log.write_text("[2026-07-23 10:00:01]: Info: CLIENT CONNECTED\n"
                   "[2026-07-23 10:00:30]: Info: CLIENT DISCONNECTED\n")
    local_tz = datetime.now().astimezone().tzinfo
    start = datetime(2026, 7, 23, 10, 0, 0, tzinfo=local_tz).astimezone(timezone.utc)
    stop = datetime(2026, 7, 23, 10, 0, 20, tzinfo=local_tz).astimezone(timezone.utc)
    out = logslice.slice_file(str(log), start, stop)
    assert "CLIENT CONNECTED" in out
    assert "CLIENT DISCONNECTED" not in out


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


def test_read_new_incremental_offsets(tmp_path):
    p = tmp_path / "app.log"
    p.write_text("first\n")
    off = logslice.file_offset(str(p))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("second\n")
    text, off2 = logslice.read_new(str(p), off)
    assert text == "second\n" and off2 > off
    # A second read from the reported offset returns only newly appended lines (no dupes).
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("third\n")
    text2, off3 = logslice.read_new(str(p), off2)
    assert text2 == "third\n" and off3 > off2
    # Nothing new -> empty, offset unchanged.
    text3, off4 = logslice.read_new(str(p), off3)
    assert text3 == "" and off4 == off3


def test_read_new_handles_rotation(tmp_path):
    p = tmp_path / "app.log"
    p.write_text("a\nb\nc\n")
    off = logslice.file_offset(str(p))
    p.write_text("x\n")  # shrank -> read from start
    text, _ = logslice.read_new(str(p), off)
    assert text == "x\n"


def test_slice_file_tail_fallback(tmp_path):
    p = tmp_path / "notimestamps.log"
    p.write_text("\n".join(f"line{i}" for i in range(5000)))
    out = logslice.slice_file(str(p), datetime(2026, 1, 1), datetime(2030, 1, 1), tail_lines=100)
    assert len(out.splitlines()) == 100
    assert "line4999" in out
