"""Deprecated-compatible hub entry point; prefer `python -m frame_relay`.

Binds to FRAME_RELAY_HOST/FRAME_RELAY_PORT (or legacy ASL_HOST/ASL_PORT) from config.
"""
from __future__ import annotations

import uvicorn

from . import config


def main() -> None:
    uvicorn.run("hub.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
