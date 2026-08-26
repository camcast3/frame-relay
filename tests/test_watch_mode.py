"""Host watch-mode helpers: follow whatever session the client created."""

import argparse

from asl_collector import client, session


def _args(**kw):
    ns = argparse.Namespace(hub_url="http://hub", source="host", role=None, machine="STREAM-HOST",
                            session_id=None, create=False, attach_latest=False, watch=False,
                            watch_interval=0.01, wg_subnet=[])
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_session_ended_when_stopped(monkeypatch):
    monkeypatch.setattr(client, "get_session", lambda hub, sid: {"id": sid, "status": "stopped"})
    assert session._session_ended("http://hub", "s1") is True


def test_session_ended_when_deleted(monkeypatch):
    monkeypatch.setattr(client, "get_session", lambda hub, sid: None)
    assert session._session_ended("http://hub", "s1") is True


def test_session_not_ended_while_active(monkeypatch):
    monkeypatch.setattr(client, "get_session", lambda hub, sid: {"id": sid, "status": "active"})
    assert session._session_ended("http://hub", "s1") is False


def test_hub_blip_does_not_end_the_session(monkeypatch):
    """A transient hub error must not abort an in-progress capture."""
    def boom(hub, sid):
        raise OSError("connection refused")
    monkeypatch.setattr(client, "get_session", boom)
    assert session._session_ended("http://hub", "s1") is False


def test_newer_session_waiting_ignores_the_current_one(monkeypatch):
    monkeypatch.setattr(client, "list_sessions",
                        lambda hub, awaiting_client=False, awaiting_host=False: [{"id": "s1"}])
    assert session._newer_session_waiting("http://hub", "s1") is False

    monkeypatch.setattr(client, "list_sessions",
                        lambda hub, awaiting_client=False, awaiting_host=False: [{"id": "s2"}])
    assert session._newer_session_waiting("http://hub", "s1") is True


def test_session_started_at_parses_and_assumes_utc(monkeypatch):
    monkeypatch.setattr(client, "get_session",
                        lambda hub, sid: {"started_at": "2026-07-25T15:03:05.972953"})
    ts = session._session_started_at("http://hub", "s1")
    assert ts is not None and ts.tzinfo is not None
    assert ts.year == 2026 and ts.hour == 15


def test_session_started_at_falls_back_to_created_at(monkeypatch):
    monkeypatch.setattr(client, "get_session",
                        lambda hub, sid: {"created_at": "2026-07-25T16:00:00+00:00"})
    ts = session._session_started_at("http://hub", "s1")
    assert ts is not None and ts.hour == 16


def test_session_started_at_handles_missing_and_bad_values(monkeypatch):
    monkeypatch.setattr(client, "get_session", lambda hub, sid: {})
    assert session._session_started_at("http://hub", "s1") is None
    monkeypatch.setattr(client, "get_session", lambda hub, sid: {"started_at": "not-a-date"})
    assert session._session_started_at("http://hub", "s1") is None
