"""Pytest fixtures: isolate the DB to a temp dir and force the offline Copilot backend."""
import os
import pathlib
import sys
import tempfile

# Make the collector package importable (it lives under collectors/, not the repo root).
_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "collectors"))
SAMPLES = _ROOT / "samples"

# Must be set before importing the hub package (config reads env at import time).
_TMP = tempfile.mkdtemp(prefix="asl-test-")
os.environ["ASL_DATA_DIR"] = _TMP
os.environ["ASL_COPILOT_BACKEND"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from hub.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
