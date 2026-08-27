#!/usr/bin/env bash
# Capture a Frame Relay session on this Linux machine (usually a Moonlight
# client such as a SteamOS/Bazzite system) and ship logs + Wi-Fi/link samples to the hub.
#
# All flags are passed straight through to `python -m frame_relay_collector` (see --help).
#
# The log path is auto-detected from --source/--role (see frame_relay_collector/logfind.py);
# pass --log
# only to override or when your install puts it somewhere unusual.
#
# Recommended (client dictates the session; a host running --watch joins it automatically).
# --launch-client makes the collector *wrap* Moonlight: it finds the app for --role, launches it,
# and captures its stderr live (the config-dir log is buffered). Capture ends when you close it.
#   ./frame-relay-session.sh --hub-url http://192.0.2.10:8080 --source client --role moonlight \
#       --create --name "couch LAN AV1" --launch-client --interval 15
#
# Attach instead to a session the host already created (no id to copy):
#   ./frame-relay-session.sh --hub-url http://192.0.2.10:8080 \
#       --source client --role moonlight --attach-latest --interval 15
#
# On a Linux Apollo host, run it long-lived and let clients dictate sessions:
#   ./frame-relay-session.sh --hub-url http://192.0.2.10:8080 --source host --watch
#
# Moonlight-Qt log locations vary by install:
#   Flatpak : ~/.var/app/com.moonlight_stream.Moonlight/  (also `flatpak run` stderr)
#   native  : ~/.config/Moonlight Game Streaming Project/
# Pass the actual path(s) with one or more --log flags if auto-detection misses yours.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTORS_DIR="$(dirname "$SCRIPT_DIR")"   # contains frame_relay_collector

PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "python3 not found; install Python 3 and re-run." >&2; exit 1; }

export PYTHONPATH="$COLLECTORS_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m frame_relay_collector "$@"
