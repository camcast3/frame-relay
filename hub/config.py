"""Runtime configuration, driven entirely by environment variables.

Set these in docker-compose (see deploy/) or your shell. Sensible defaults let the
hub run locally with zero configuration.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env(
    name: str,
    legacy_name: str,
    default: str | None = None,
    *,
    allow_empty: bool = False,
) -> str | None:
    if name in os.environ:
        value = os.environ[name]
        if value or allow_empty:
            return value
    if legacy_name in os.environ:
        legacy = os.environ[legacy_name]
        if legacy or allow_empty:
            return legacy
    return default


# Where the SQLite database and uploaded artifacts live. In the container this is a
# mounted volume (/data); locally it defaults to ./data next to the repo.
_default_data_dir = os.environ.get(
    "FRAME_RELAY_DEFAULT_DATA_DIR",
    str(Path(__file__).resolve().parent.parent / "data"),
)
DATA_DIR = Path(
    _env(
        "FRAME_RELAY_DATA_DIR",
        "ASL_DATA_DIR",
        _default_data_dir,
    )
)
_default_db = DATA_DIR / "frame-relay.db"
_legacy_db = DATA_DIR / "asl.db"
DB_PATH = Path(
    _env(
        "FRAME_RELAY_DB_PATH",
        "ASL_DB_PATH",
        str(_default_db if _default_db.exists() or not _legacy_db.exists() else _legacy_db),
    )
)
ARTIFACTS_DIR = Path(
    _env("FRAME_RELAY_ARTIFACTS_DIR", "ASL_ARTIFACTS_DIR", str(DATA_DIR / "artifacts"))
)

# HTTP bind. Behind the Tailscale sidecar the container listens on all interfaces and
# `tailscale serve` publishes it to the tailnet only.
HOST = str(_env("FRAME_RELAY_HOST", "ASL_HOST", "0.0.0.0"))
PORT = int(str(_env("FRAME_RELAY_PORT", "ASL_PORT", "8080")))

# Copilot analysis backend: "mock" (offline, rule-based), "cli" (shell out to the
# Copilot CLI programmatic mode), or "sdk" (embed the Copilot Python SDK).
COPILOT_BACKEND = str(
    _env("FRAME_RELAY_COPILOT_BACKEND", "ASL_COPILOT_BACKEND", "mock")
).lower()
COPILOT_MODEL = str(_env("FRAME_RELAY_COPILOT_MODEL", "ASL_COPILOT_MODEL", "auto"))
# Token with a Copilot entitlement, used by the cli/sdk backends. Provide via secret.
COPILOT_TOKEN = (
    _env(
        "FRAME_RELAY_COPILOT_TOKEN",
        "ASL_COPILOT_TOKEN",
        allow_empty=True,
    )
    or os.environ.get("GITHUB_TOKEN")
)
# Path to the copilot binary for the "cli" backend.
COPILOT_CLI_PATH = str(
    _env("FRAME_RELAY_COPILOT_CLI_PATH", "ASL_COPILOT_CLI_PATH", "copilot")
)

# Shared-secret auth for the optional screenshot-request workflow.
SCREENSHOT_TOKEN = str(
    _env(
        "FRAME_RELAY_SCREENSHOT_TOKEN",
        "ASL_SCREENSHOT_TOKEN",
        "",
        allow_empty=True,
    )
).strip()
# Maximum accepted PNG size for screenshot-request uploads.
SCREENSHOT_MAX_UPLOAD_BYTES = int(
    str(
        _env(
            "FRAME_RELAY_SCREENSHOT_MAX_UPLOAD_BYTES",
            "ASL_SCREENSHOT_MAX_UPLOAD_BYTES",
            str(25 * 1024 * 1024),
        )
    )
)

# How many trailing log lines per source to include in a Copilot prompt.
COPILOT_LOG_TAIL_LINES = int(
    str(
        _env(
            "FRAME_RELAY_COPILOT_LOG_TAIL_LINES",
            "ASL_COPILOT_LOG_TAIL_LINES",
            "400",
        )
    )
)


def ensure_dirs() -> None:
    """Create the data and artifact directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
