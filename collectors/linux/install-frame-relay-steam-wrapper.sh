#!/usr/bin/env bash
# Install/update the user-local Steam wrapper. Prompts for Moonlight or Artemis when omitted.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTORS_DIR="$(dirname "$SCRIPT_DIR")"
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "Python 3 is required for Frame Relay." >&2; exit 1; }

export PYTHONPATH="$COLLECTORS_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m frame_relay_collector.steamsetup "$@"
