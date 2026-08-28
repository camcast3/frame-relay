#!/usr/bin/env bash
# Steam Launch Options: "$HOME/.local/bin/frame-relay-steam-launch" -- %command%
set -euo pipefail

DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/frame-relay"
CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/frame-relay"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/frame-relay"

PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "Python 3 is required for Frame Relay." >&2; exit 1; }

export PYTHONPATH="$DATA_ROOT/lib"
exec "$PY" -m frame_relay_collector.steamlaunch \
  --config "$CONFIG_ROOT/steam-launch.json" \
  --log-file "$STATE_ROOT/steam-launch.log" \
  "$@"
