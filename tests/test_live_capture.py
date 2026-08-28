"""Live-capture helpers: launched-app stderr reader + live client-IP accessor."""
import io
import threading

from frame_relay_collector import conninfo, session


def test_reader_drains_stream_into_buffer():
    stream = io.StringIO("line one\nline two\nline three\n")
    buf: list[str] = []
    session._reader(stream, buf, threading.Lock())
    assert buf == ["line one\n", "line two\n", "line three\n"]


def test_reader_stops_at_eof_without_error():
    buf: list[str] = []
    session._reader(io.StringIO(""), buf, threading.Lock())
    assert buf == []


def test_client_monitor_current_returns_most_common():
    m = conninfo.ClientMonitor([47989])
    m.seen = ["1.2.3.4", "1.2.3.4", "5.6.7.8"]
    assert m.current() == "1.2.3.4"


def test_client_monitor_current_none_when_empty():
    assert conninfo.ClientMonitor([47989]).current() is None
