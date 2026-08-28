#!/usr/bin/env bash
# Deprecated compatibility wrapper. Use frame-relay-session.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/frame-relay-session.sh" "$@"
