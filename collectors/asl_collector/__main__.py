"""Deprecated `python -m asl_collector` compatibility entry point."""
from __future__ import annotations

from frame_relay_collector.session import main

if __name__ == "__main__":
    main()
