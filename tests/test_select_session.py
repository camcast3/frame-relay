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


def test_select_session_auto_picks_only_session(monkeypatch):
    monkeypatch.setattr(client, "list_sessions",
                        lambda hub, awaiting_client=False: [
                            {"id": "s1", "name": "one", "host": "DOMINO", "created_at": "2026-07-23T10:00:00"},
                        ])
    # No input() should be needed when only one session awaits a client.
    monkeypatch.setattr(builtins, "input", lambda *_: (_ for _ in ()).throw(AssertionError("prompted")))
    assert session._select_session("http://hub") == "s1"


def test_attach_latest_picks_newest_without_prompt(monkeypatch):
    # list_sessions(awaiting_client=True) returns newest first.
    monkeypatch.setattr(client, "list_sessions",
                        lambda hub, awaiting_client=False: [
                            {"id": "s2", "name": "two", "host": "DOMINO", "created_at": "2026-07-23T10:05:00"},
                            {"id": "s1", "name": "one", "host": "DOMINO", "created_at": "2026-07-23T10:00:00"},
                        ])
    monkeypatch.setattr(builtins, "input", lambda *_: (_ for _ in ()).throw(AssertionError("prompted")))
    assert session._select_session("http://hub", attach_latest=True) == "s2"


def test_select_session_multiple_no_tty_errors(monkeypatch):
    monkeypatch.setattr(client, "list_sessions",
                        lambda hub, awaiting_client=False: [
                            {"id": "s2", "name": "two", "host": "DOMINO", "created_at": "2026-07-23T10:05:00"},
                            {"id": "s1", "name": "one", "host": "DOMINO", "created_at": "2026-07-23T10:00:00"},
                        ])
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    try:
        session._select_session("http://hub")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "--attach-latest" in str(e)
