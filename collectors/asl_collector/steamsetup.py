"""Deprecated compatibility entry point for Frame Relay Steam setup."""
from __future__ import annotations

from frame_relay_collector.steamsetup import *  # noqa: F403
from frame_relay_collector.steamsetup import main

if __name__ == "__main__":
    main()
