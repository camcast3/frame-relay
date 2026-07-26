"""Session resolution for the iperf3 runner (posting used to silently no-op)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "network"))
import iperf_runner  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_newest_active_session_picks_first_active(monkeypatch):
    payload = [
        {"id": "s3", "status": "stopped"},   # newest, but finished
        {"id": "s2", "status": "active"},
        {"id": "s1", "status": "active"},
    ]
    monkeypatch.setattr(iperf_runner.urllib.request, "urlopen",
                        lambda url, timeout=15: _Resp(payload))
    assert iperf_runner.newest_active_session("http://hub") == "s2"


def test_newest_active_session_none_when_all_stopped(monkeypatch):
    monkeypatch.setattr(iperf_runner.urllib.request, "urlopen",
                        lambda url, timeout=15: _Resp([{"id": "s1", "status": "stopped"}]))
    assert iperf_runner.newest_active_session("http://hub") is None


def test_newest_active_session_survives_unreachable_hub(monkeypatch):
    def boom(url, timeout=15):
        raise OSError("connection refused")
    monkeypatch.setattr(iperf_runner.urllib.request, "urlopen", boom)
    assert iperf_runner.newest_active_session("http://hub") is None


def test_session_id_without_hub_url_is_rejected(monkeypatch):
    """Silently doing nothing is what made a run look successful while nothing was recorded."""
    monkeypatch.setattr(sys, "argv",
                        ["iperf_runner.py", "--host", "1.2.3.4", "--session-id", "abc"])
    with pytest.raises(SystemExit) as e:
        iperf_runner.main()
    assert e.value.code != 0


def test_missing_iperf3_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["iperf_runner.py", "--host", "1.2.3.4"])

    def boom(*a, **kw):
        raise RuntimeError("iperf3 is not installed or not on PATH. Install iperf3 and try again.")
    monkeypatch.setattr(iperf_runner, "run_iperf3", boom)

    with pytest.raises(SystemExit) as e:
        iperf_runner.main()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "iperf3 is not installed" in err
    assert "iperf3 -s" in err          # tells them what to do next


def test_result_is_posted_and_confirmed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["iperf_runner.py", "--host", "1.2.3.4",
                                      "--hub-url", "http://hub", "--session-id", "s1"])
    monkeypatch.setattr(iperf_runner, "run_iperf3",
                        lambda *a, **kw: {"loss_pct": 1.0, "jitter_ms": 0.2})
    posted = {}
    monkeypatch.setattr(iperf_runner, "post_to_hub",
                        lambda hub, sid, res: posted.update(hub=hub, sid=sid, res=res))
    iperf_runner.main()
    assert posted["sid"] == "s1"
    assert "posted to" in capsys.readouterr().out
