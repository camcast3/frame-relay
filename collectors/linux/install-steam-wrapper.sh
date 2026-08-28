#!/usr/bin/env bash
# Deprecated compatibility wrapper. Use install-frame-relay-steam-wrapper.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/install-frame-relay-steam-wrapper.sh" "$@"
