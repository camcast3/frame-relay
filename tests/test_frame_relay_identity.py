"""Canonical Frame Relay identity and migration behavior."""
from __future__ import annotations

import runpy
from pathlib import Path

from hub.main import app

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "hub" / "config.py"


def _load_config(monkeypatch, data_dir: Path | None, **environment: str):
    names = {
        "FRAME_RELAY_DATA_DIR",
        "FRAME_RELAY_DEFAULT_DATA_DIR",
        "FRAME_RELAY_DB_PATH",
        "FRAME_RELAY_COPILOT_BACKEND",
        "FRAME_RELAY_SCREENSHOT_TOKEN",
        "ASL_DATA_DIR",
        "ASL_DB_PATH",
        "ASL_COPILOT_BACKEND",
        "ASL_SCREENSHOT_TOKEN",
    }
    for name in names:
        monkeypatch.delenv(name, raising=False)
    if data_dir is not None:
        monkeypatch.setenv("FRAME_RELAY_DATA_DIR", str(data_dir))
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(str(CONFIG_PATH))


def test_fastapi_uses_frame_relay_title():
    assert app.title == "Frame Relay"


def test_new_environment_name_wins_over_legacy(monkeypatch, tmp_path):
    config = _load_config(
        monkeypatch,
        tmp_path,
        FRAME_RELAY_COPILOT_BACKEND="sdk",
        ASL_COPILOT_BACKEND="cli",
    )

    assert config["COPILOT_BACKEND"] == "sdk"


def test_legacy_environment_name_is_fallback(monkeypatch, tmp_path):
    config = _load_config(
        monkeypatch,
        tmp_path,
        ASL_COPILOT_BACKEND="cli",
    )

    assert config["COPILOT_BACKEND"] == "cli"


def test_new_install_uses_frame_relay_database_name(monkeypatch, tmp_path):
    config = _load_config(monkeypatch, tmp_path)

    assert config["DB_PATH"] == tmp_path / "frame-relay.db"


def test_existing_legacy_database_is_preserved(monkeypatch, tmp_path):
    legacy = tmp_path / "asl.db"
    legacy.write_bytes(b"legacy")

    config = _load_config(monkeypatch, tmp_path)

    assert config["DB_PATH"] == legacy


def test_container_default_does_not_mask_legacy_data_dir(monkeypatch, tmp_path):
    legacy_dir = tmp_path / "legacy"
    config = _load_config(
        monkeypatch,
        None,
        FRAME_RELAY_DEFAULT_DATA_DIR="/data",
        ASL_DATA_DIR=str(legacy_dir),
    )

    assert config["DATA_DIR"] == legacy_dir


def test_explicit_empty_new_screenshot_token_disables_legacy(monkeypatch, tmp_path):
    config = _load_config(
        monkeypatch,
        tmp_path,
        FRAME_RELAY_SCREENSHOT_TOKEN="",
        ASL_SCREENSHOT_TOKEN="legacy-secret",
    )

    assert config["SCREENSHOT_TOKEN"] == ""
