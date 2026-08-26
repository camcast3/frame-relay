"""Client-app discovery for --launch-client (pure candidate lists, no filesystem)."""
import os

from asl_collector import appfind

WIN_ENV = {
    "ProgramFiles": r"C:\Program Files",
    "ProgramFiles(x86)": r"C:\Program Files (x86)",
    "LOCALAPPDATA": r"C:\Users\tester\AppData\Local",
}


def test_windows_artemis_candidates():
    got = appfind.candidate_apps("artemis", system="Windows", env=WIN_ENV, home=r"C:\Users\tester")
    # the normal system-wide install location must be first
    assert got[0] == r"C:\Program Files\Artemis Game Streaming\Artemis.exe"
    assert r"C:\Program Files (x86)\Artemis Game Streaming\Artemis.exe" in got
    assert all(p.endswith("Artemis.exe") for p in got)


def test_windows_moonlight_candidates():
    got = appfind.candidate_apps("moonlight", system="Windows", env=WIN_ENV, home=r"C:\Users\tester")
    assert got[0] == r"C:\Program Files\Moonlight Game Streaming\Moonlight.exe"
    assert all(p.endswith("Moonlight.exe") for p in got)


def test_windows_roles_do_not_cross_over():
    artemis = appfind.candidate_apps("artemis", system="Windows", env=WIN_ENV, home="C:\\h")
    moonlight = appfind.candidate_apps("moonlight", system="Windows", env=WIN_ENV, home="C:\\h")
    assert not set(artemis) & set(moonlight)


def test_linux_prefers_flatpak_export():
    got = appfind.candidate_apps("moonlight", system="Linux", env={}, home="/home/tester")
    assert got[0] == ("/home/tester/.local/share/flatpak/exports/bin/"
                      "com.moonlight_stream.Moonlight")
    assert "/usr/bin/moonlight" in got


def test_unknown_role_has_no_candidates():
    assert appfind.candidate_apps("apollo", system="Windows", env=WIN_ENV, home="C:\\h") == []
    assert appfind.candidate_apps("", system="Linux", env={}, home="/home/x") == []


def test_discover_returns_first_existing_executable(tmp_path, monkeypatch):
    missing = tmp_path / "nope" / "Artemis.exe"
    real = tmp_path / "Artemis Game Streaming" / "Artemis.exe"
    real.parent.mkdir(parents=True)
    real.write_text("#!/bin/sh\n")
    real.chmod(0o755)

    monkeypatch.setattr(appfind, "candidate_apps",
                        lambda role, **kw: [str(missing), str(real)])
    assert appfind.discover("artemis") == str(real)


def test_discover_returns_none_when_nothing_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(appfind, "candidate_apps",
                        lambda role, **kw: [str(tmp_path / "absent.exe")])
    assert appfind.discover("artemis") is None


def test_discover_skips_a_directory_named_like_the_app(tmp_path, monkeypatch):
    """os.access(X_OK) is true for directories - the isfile check must catch that."""
    decoy = tmp_path / "Artemis.exe"
    decoy.mkdir()
    monkeypatch.setattr(appfind, "candidate_apps", lambda role, **kw: [str(decoy)])
    assert appfind.discover("artemis") is None
