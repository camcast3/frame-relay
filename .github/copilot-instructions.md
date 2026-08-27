# Frame Relay — Copilot instructions

Keep this file short, authoritative, and mandatory. Put rationale and durable implementation detail in the maintainer docs:

- [Maintainer guide](../docs/maintainer/README.md)
- [Architecture](../docs/maintainer/architecture.md)
- [Development](../docs/maintainer/development.md)
- [API and data model](../docs/maintainer/api-and-data-model.md)
- [Collectors and parsers](../docs/maintainer/collectors-and-parsers.md)
- [Copilot backends](../docs/maintainer/copilot-backends.md)
- [Security and operations](../docs/maintainer/security-and-operations.md)

## Commands

Python 3.11. Windows-first repo. The hub deploys on Linux Docker.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt

.\.venv\Scripts\python.exe -m uvicorn hub.main:app --reload --port 8080
.\.venv\Scripts\python.exe -m frame_relay

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_linkinfo.py::test_parse_netsh_wlan

docker compose -f docker-compose.lan.yaml up -d --build
```

Bare `uvicorn hub.main:app` binds `127.0.0.1` only. Use `python -m frame_relay` (or pass `--host 0.0.0.0`) for other devices.

## Mandatory rules

- Respect the hub layering: routers (`sessions`, `ingest`, `analysis`, `screenshot_requests`) → `service.py` → `db.py`. Keep HTTP concerns in routers and SQLite concerns in `db.py`.
- Treat `hub/models.py` as the shared API contract for collectors, DB-backed session state, templates, and JS. A field change there is never isolated.
- `hub/config.py` is env-only and reads `FRAME_RELAY_*` values at import time. Set env before importing `hub`.
- Keep DB access synchronous and connection-per-call through `db.db()`. Session JSON columns stay stored as TEXT and are decoded in `row_to_dict`.
- The session is the central entity. Child tables (`log_chunks`, `link_samples`, `display_samples`, `net_tests`, `artifacts`, `screenshot_requests`, `chat_messages`) hang off it.
- Anything under `collectors/frame_relay_collector/` must stay standard-library only. Use `urllib`, never `requests`/`httpx`.
- Preserve the parser/runner split. Discovery lives in `logfind.py` and `appfind.py`; parsing stays testable from captured text; new OS/command support needs a sample and a test.
- Reuse the fixed network-path literals only: `local-LAN`, `remote-WireGuard`, `remote-Tailscale`, `remote-WAN`.
- The host collector fills blank effective/session fields live and never overwrites values already supplied by the UI or CLI.
- “Awaiting a host/client” means that source has posted no log chunk yet, not that the host/client name field is blank.
- Windows display capture must run in a logged-in interactive session. `QueryDisplayConfig` is not supported from SYSTEM/non-interactive service sessions.
- Screenshot requests are optional and security-sensitive: keep `FRAME_RELAY_SCREENSHOT_TOKEN` as the shared secret, require `X-Frame-Relay-Screenshot-Token` on screenshot-request endpoints, accept PNG only for requested screenshots, and remember that completed screenshots become normal `/artifacts` files visible to anyone who can reach the hub.
- Screenshots, log-derived HDR evidence, and operator ratings are useful visual evidence, not objective HDR measurement. Windows may tone-map HDR capture and protected surfaces may appear black.
- No linter/formatter is configured; do not add one unless asked.
- Every module starts with `from __future__ import annotations`.
- `data/` and `.env` are gitignored; never commit either.
- Dependency updates use exact hash locks and a seven-day release holdback. Regenerate through
  `tools/lock_requirements.py`, verify with `tools/lock_requirements.py --check`, and never
  hand-edit lock versions/hashes. Runtime images must be
  version+digest pinned and pass the critical/high container scan. Tailnet Compose must remain
  fail-closed when no reviewed Tailscale image satisfies that policy.

## Tests

- `tests/conftest.py` prepends `collectors/` to `sys.path`, sets `FRAME_RELAY_DATA_DIR`, `FRAME_RELAY_COPILOT_BACKEND=mock`, and `FRAME_RELAY_SCREENSHOT_TOKEN`, then imports `hub`.
- Prefer the smallest targeted pytest selection that covers the change.
