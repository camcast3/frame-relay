"""Interactive awaiting-client session picker in the collector."""
import builtins

from asl_collector import client, session


def test_select_session_picks_by_number(monkeypatch):
    monkeypatch.setattr(client, "list_sessions",
                        lambda hub, awaiting_client=False: [
                            {"id": "s1", "name": "one", "host": "DOMINO", "created_at": "2026-07-23T10:00:00"},
                            {"id": "s2", "name": "two", "host": "DOMINO", "created_at": "2026-07-23T10:05:00"},
                        ])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr(builtins, "input", lambda *_: "2")
    assert session._select_session("http://hub") == "s2"


def test_select_session_none_available(monkeypatch):
    monkeypatch.setattr(client, "list_sessions", lambda hub, awaiting_client=False: [])
    try:
        session._select_session("http://hub")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "awaiting a client" in str(e)
