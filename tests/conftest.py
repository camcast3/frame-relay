"""Pytest fixtures: isolate the DB and force the offline Copilot backend."""
from __future__ import annotations

import atexit
import os
import pathlib
import shutil
import sys
import uuid

# Make the collector package importable (it lives under collectors/, not the repo root).
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "collectors"))
SAMPLES = _ROOT / "samples"

# Must be set before importing the hub package (config reads env at import time).
_TEST_DATA_DIR = _ROOT / ".testdata" / uuid.uuid4().hex
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
atexit.register(lambda: shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True))

os.environ["FRAME_RELAY_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["FRAME_RELAY_COPILOT_BACKEND"] = "mock"
os.environ["FRAME_RELAY_SCREENSHOT_TOKEN"] = "test-screenshot-token"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from hub.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
