"""Run the Frame Relay hub with `python -m frame_relay`."""
from __future__ import annotations

import uvicorn

from hub import config


def main() -> None:
    uvicorn.run("hub.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
