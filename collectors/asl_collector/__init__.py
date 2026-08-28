"""Deprecated compatibility package for :mod:`frame_relay_collector`."""
from __future__ import annotations

import importlib
import sys

from frame_relay_collector import __version__

_SUBMODULES = (
    "appfind",
    "client",
    "clientmeta",
    "conninfo",
    "displayprobe",
    "hostmeta",
    "linkinfo",
    "logfind",
    "logslice",
    "netmon",
    "screenshot",
    "session",
)

for _name in _SUBMODULES:
    _module = importlib.import_module(f"frame_relay_collector.{_name}")
    globals()[_name] = _module
    sys.modules[f"{__name__}.{_name}"] = _module

__all__ = ["__version__", *_SUBMODULES, "steamlaunch", "steamsetup"]
