#!/usr/bin/env bash
# Capture an Apollo Streaming Lab session on this Linux machine (usually a Moonlight
# client such as the Bazzite couch box) and ship logs + Wi-Fi/link samples to the hub.
#
# All flags are passed straight through to `python -m asl_collector` (see --help).
#
# Example (Moonlight client, create the session, sample link every 15s until Enter):
#   ./asl-session.sh --hub-url https://apollo-streaming-lab.<tailnet>.ts.net --create \
#       --name "couch LAN HEVC" --host DOMINO --client couch --network-path local-LAN \
#       --source client --role moonlight --interval 15 \
#       --log "$HOME/.var/app/com.moonlight_stream.Moonlight/config/Moonlight Game Streaming Project/Moonlight.conf"
#
# Example (Moonlight client, zero copy-paste: attach to the newest session the host created):
#   ./asl-session.sh --hub-url https://apollo-streaming-lab.<tailnet>.ts.net \
#       --source client --role moonlight --attach-latest --interval 15 \
#       --log "$HOME/.var/app/com.moonlight_stream.Moonlight/config/Moonlight Game Streaming Project/Moonlight.conf"
#
# Moonlight-Qt log locations vary by install:
#   Flatpak : ~/.var/app/com.moonlight_stream.Moonlight/  (also `flatpak run` stderr)
#   native  : ~/.config/Moonlight Game Streaming Project/
# Pass the actual path(s) with one or more --log flags.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTORS_DIR="$(dirname "$SCRIPT_DIR")"   # contains the asl_collector package

PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "python3 not found; install Python 3 and re-run." >&2; exit 1; }

export PYTHONPATH="$COLLECTORS_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m asl_collector "$@"
