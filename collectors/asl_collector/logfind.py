"""Role-driven log-location discovery (standard library only).

Given the capture *source* (host/client) and *role* (apollo/moonlight/artemis) this maps to the
known log paths per platform, so a client never has to know or type where its log lives - the
collector finds it from the role the operator selected.

Kept split from the runner (like the parsers): :func:`candidate_paths` is a pure function of
``(source, role, system, env, home)`` so it can be unit-tested with fixtures; :func:`discover`
does the filesystem glob + newest-file selection.
"""
from __future__ import annotations

import glob
import ntpath
import os
import platform
import posixpath
from typing import Mapping, Optional


def candidate_paths(source: str, role: str, *, system: Optional[str] = None,
                    env: Optional[Mapping[str, str]] = None,
                    home: Optional[str] = None) -> list[str]:
    """Return the candidate log path(s)/glob(s) for a capture source + role on a platform.

    Paths are ordered most- to least-preferred. Returns ``[]`` when no convention is known
    (e.g. Moonlight-Qt on Windows, whose only fixed ``%TEMP%`` file is the installer log).
    """
    system = system or platform.system()
    env = os.environ if env is None else env
    home = home if home is not None else os.path.expanduser("~")
    win = system == "Windows"
    join = ntpath.join if win else posixpath.join
    role = (role or "").lower()
    source = (source or "").lower()
    out: list[str] = []

    # Apollo / Sunshine host.
    if source == "host" or role == "apollo":
        if win:
            pf = env.get("ProgramFiles", r"C:\Program Files")
            pf86 = env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            out += [
                fr"{pf}\Apollo\config\sunshine.log",
                fr"{pf86}\Apollo\config\sunshine.log",
                fr"{pf}\Sunshine\config\sunshine.log",
            ]
        else:
            out += [
                join(home, ".config", "sunshine", "sunshine.log"),
                "/var/log/sunshine/sunshine.log",
            ]
        return out

    # Artemis client (Apollo's Moonlight fork) writes a per-run log into %TEMP% on Windows.
    if role == "artemis":
        if win:
            tmp = env.get("TEMP") or env.get("TMP")
            if tmp:
                out.append(join(tmp, "Artemis-*.log"))
        return out

    # Moonlight-Qt client. No reliable auto path on Windows (use "Copy diagnostic logs"); on
    # Linux the Flatpak/native config dirs hold the log.
    if role == "moonlight":
        if not win:
            out += [
                join(home, ".var", "app", "com.moonlight_stream.Moonlight",
                     "config", "Moonlight Game Streaming Project", "*.log"),
                join(home, ".var", "app", "com.moonlight_stream.Moonlight", "*.log"),
                join(home, ".config", "Moonlight Game Streaming Project", "*.log"),
            ]
        return out

    return out


def discover(source: str, role: str, **kw) -> list[str]:
    """Resolve :func:`candidate_paths` against the filesystem.

    Returns the single newest existing log file (so globs like ``Artemis-*.log`` pick the latest
    run), or ``[]`` when nothing matches.
    """
    matches: list[str] = []
    for pattern in candidate_paths(source, role, **kw):
        matches.extend(glob.glob(pattern))
    existing = [p for p in matches if os.path.isfile(p)]
    if not existing:
        return []
    newest = max(existing, key=lambda p: os.path.getmtime(p))
    return [newest]
