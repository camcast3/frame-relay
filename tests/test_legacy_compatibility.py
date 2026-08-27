"""Compatibility checks for the retired Apollo Streaming Lab interfaces."""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

from frame_relay_collector import client as frame_relay_client
from hub import config

ROOT = Path(__file__).resolve().parent.parent


def test_legacy_collector_package_aliases_canonical_modules():
    legacy_client = importlib.import_module("asl_collector.client")

    assert legacy_client is frame_relay_client


def test_legacy_environment_names_remain_supported(monkeypatch):
    monkeypatch.delenv("FRAME_RELAY_COPILOT_BACKEND", raising=False)
    monkeypatch.setenv("ASL_COPILOT_BACKEND", "cli")

    assert config._env(
        "FRAME_RELAY_COPILOT_BACKEND", "ASL_COPILOT_BACKEND", "mock"
    ) == "cli"


def test_legacy_screenshot_header_remains_supported(client):
    created = client.post(
        "/api/sessions",
        json={"name": "legacy-header", "host": "host", "client": "client"},
    ).json()

    response = client.post(
        f"/api/sessions/{created['id']}/screenshot-requests",
        json={"targets": ["host"]},
        headers={"X-ASL-Screenshot-Token": config.SCREENSHOT_TOKEN},
    )

    assert response.status_code == 200


def test_legacy_steam_submodule_commands_still_run():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "collectors")
    for module in ("asl_collector.steamlaunch", "asl_collector.steamsetup"):
        result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
