"""Runtime configuration, driven entirely by environment variables.

Set these in docker-compose (see deploy/) or your shell. Sensible defaults let the
hub run locally with zero configuration.
"""
from __future__ import annotations

import os
from pathlib import Path

# Where the SQLite database and uploaded artifacts live. In the container this is a
# mounted volume (/data); locally it defaults to ./data next to the repo.
DATA_DIR = Path(os.environ.get("ASL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = Path(os.environ.get("ASL_DB_PATH", DATA_DIR / "asl.db"))
ARTIFACTS_DIR = Path(os.environ.get("ASL_ARTIFACTS_DIR", DATA_DIR / "artifacts"))

# HTTP bind. Behind the Tailscale sidecar the container listens on all interfaces and
# `tailscale serve` publishes it to the tailnet only.
HOST = os.environ.get("ASL_HOST", "0.0.0.0")
PORT = int(os.environ.get("ASL_PORT", "8080"))

# Copilot analysis backend: "mock" (offline, rule-based), "cli" (shell out to the
# Copilot CLI programmatic mode), or "sdk" (embed the Copilot Python SDK).
COPILOT_BACKEND = os.environ.get("ASL_COPILOT_BACKEND", "mock").lower()
COPILOT_MODEL = os.environ.get("ASL_COPILOT_MODEL", "auto")
# Token with a Copilot entitlement, used by the cli/sdk backends. Provide via secret.
COPILOT_TOKEN = os.environ.get("ASL_COPILOT_TOKEN") or os.environ.get("GITHUB_TOKEN")
# Path to the copilot binary for the "cli" backend.
COPILOT_CLI_PATH = os.environ.get("ASL_COPILOT_CLI_PATH", "copilot")

# How many trailing log lines per source to include in a Copilot prompt.
COPILOT_LOG_TAIL_LINES = int(os.environ.get("ASL_COPILOT_LOG_TAIL_LINES", "400"))


def ensure_dirs() -> None:
    """Create the data and artifact directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
