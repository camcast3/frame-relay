"""Deprecated compatibility entry point for Frame Relay Steam launches."""
from __future__ import annotations

from frame_relay_collector.steamlaunch import *  # noqa: F403
from frame_relay_collector.steamlaunch import main

if __name__ == "__main__":
    main()
