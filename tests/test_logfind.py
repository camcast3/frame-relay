"""Role-driven log-location discovery in the collector."""
from frame_relay_collector import logfind


def test_apollo_host_windows_candidates():
    paths = logfind.candidate_paths(
        "host", "apollo", system="Windows",
        env={"ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)"},
        home=r"C:\Users\x",
    )
    assert paths[0] == r"C:\Program Files\Apollo\config\sunshine.log"
    assert r"C:\Program Files (x86)\Apollo\config\sunshine.log" in paths
    assert any("Sunshine" in p for p in paths)


def test_apollo_host_linux_candidates():
    paths = logfind.candidate_paths("host", "apollo", system="Linux", env={}, home="/home/x")
    assert "/home/x/.config/sunshine/sunshine.log" in paths


def test_artemis_windows_uses_temp_glob():
    paths = logfind.candidate_paths("client", "artemis", system="Windows",
                                    env={"TEMP": r"C:\Temp"}, home=r"C:\Users\x")
    assert paths == [r"C:\Temp\Artemis-*.log"]


def test_moonlight_windows_has_no_auto_path():
    # Moonlight-Qt on Windows: the only fixed %TEMP% file is the installer log, so no auto path.
    assert logfind.candidate_paths("client", "moonlight", system="Windows",
                                   env={"TEMP": r"C:\Temp"}, home=r"C:\Users\x") == []


def test_moonlight_linux_candidates():
    paths = logfind.candidate_paths("client", "moonlight", system="Linux", env={}, home="/home/x")
    assert any(".var/app/com.moonlight_stream.Moonlight" in p for p in paths)
    assert any("Moonlight Game Streaming Project" in p for p in paths)
    assert all(p.endswith("*.log") for p in paths)


def test_discover_picks_newest_existing(tmp_path, monkeypatch):
    old = tmp_path / "Artemis-1.log"
    new = tmp_path / "Artemis-2.log"
    old.write_text("old")
    new.write_text("new")
    import os
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    monkeypatch.setattr(logfind, "candidate_paths",
                        lambda *a, **k: [str(tmp_path / "Artemis-*.log")])
    assert logfind.discover("client", "artemis") == [str(new)]


def test_discover_returns_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(logfind, "candidate_paths",
                        lambda *a, **k: [str(tmp_path / "nope-*.log")])
    assert logfind.discover("client", "artemis") == []
