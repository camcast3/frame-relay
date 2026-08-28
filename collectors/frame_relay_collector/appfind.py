"""Role-driven client-app discovery (standard library only).

The mirror of :mod:`logfind` for executables. Launching the client app *through* the collector
is the only way to get its log live - Qt writes diagnostics to stderr in real time, while the
``%TEMP%`` file it also keeps is buffered and only flushes in bursts. Discovering the binary from
the role means the operator never has to type an install path to get that.

Kept split from the runner like the parsers: :func:`candidate_apps` is a pure function of
``(role, system, env, home)`` so it can be unit-tested with fixtures; :func:`discover` does the
filesystem check.
"""
from __future__ import annotations

import ntpath
import os
import platform
import posixpath
from typing import Mapping, Optional


def candidate_apps(role: str, *, system: Optional[str] = None,
                   env: Optional[Mapping[str, str]] = None,
                   home: Optional[str] = None) -> list[str]:
    """Return candidate executable paths for a client role, most- to least-preferred."""
    system = system or platform.system()
    env = os.environ if env is None else env
    home = home if home is not None else os.path.expanduser("~")
    win = system == "Windows"
    join = ntpath.join if win else posixpath.join
    role = (role or "").lower()
    out: list[str] = []

    if win:
        pf = env.get("ProgramFiles", r"C:\Program Files")
        pf86 = env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = env.get("LOCALAPPDATA") or join(home, "AppData", "Local")
        if role == "artemis":
            out += [
                join(pf, "Artemis Game Streaming", "Artemis.exe"),
                join(pf86, "Artemis Game Streaming", "Artemis.exe"),
                join(local, "Programs", "Artemis Game Streaming", "Artemis.exe"),
            ]
        elif role == "moonlight":
            out += [
                join(pf, "Moonlight Game Streaming", "Moonlight.exe"),
                join(pf86, "Moonlight Game Streaming", "Moonlight.exe"),
                join(local, "Programs", "Moonlight Game Streaming", "Moonlight.exe"),
            ]
        return out

    # Linux: the Flatpak export is a real executable path, so it can be launched directly.
    if role in ("moonlight", "artemis"):
        out += [
            join(home, ".local", "share", "flatpak", "exports", "bin",
                 "com.moonlight_stream.Moonlight"),
            "/var/lib/flatpak/exports/bin/com.moonlight_stream.Moonlight",
            "/usr/bin/moonlight",
            "/usr/local/bin/moonlight",
        ]
    return out


def discover(role: str, **kw) -> Optional[str]:
    """First candidate app that exists and is executable, or ``None``."""
    for path in candidate_apps(role, **kw):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None
