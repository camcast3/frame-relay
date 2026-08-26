#!/usr/bin/env bash
# Steam Launch Options: "$HOME/.local/bin/asl-steam-launch" -- %command%
set -euo pipefail

DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/apollo-streaming-lab"
CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/apollo-streaming-lab"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/apollo-streaming-lab"

PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "Python 3 is required for Apollo Streaming Lab." >&2; exit 1; }

export PYTHONPATH="$DATA_ROOT/lib"
exec "$PY" -m asl_collector.steamlaunch \
  --config "$CONFIG_ROOT/steam-launch.json" \
  --log-file "$STATE_ROOT/steam-launch.log" \
  "$@"
