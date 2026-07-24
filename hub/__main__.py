"""Run the hub with `python -m hub`.

Binds to ASL_HOST/ASL_PORT from config (default 0.0.0.0:8080) so the hub is reachable from
other devices, unlike a bare `uvicorn hub.main:app` which defaults to 127.0.0.1 only.
"""
from __future__ import annotations

import uvicorn

from . import config


def main() -> None:
    uvicorn.run("hub.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
