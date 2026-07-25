# Apollo Streaming Lab — Copilot instructions

A troubleshooting/test harness for **Apollo/Sunshine** (host) ↔ **Moonlight/Artemis** (clients)
game streaming. A **session** links, in one place, the host log + client log (side-by-side),
the scenario config, network diagnostics (iperf3), sampled Wi-Fi/link info, operator notes, and
an on-demand Copilot analysis.

## Commands

Python 3.11. Windows-first repo (PowerShell examples, `.ps1` collector); the hub deploys on Linux Docker.

```powershell
# setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# run the hub (dev) — reachable only from this machine (127.0.0.1)
.\.venv\Scripts\python.exe -m uvicorn hub.main:app --reload --port 8080
# run the hub bound to 0.0.0.0:8080 (reachable from other devices)
.\.venv\Scripts\python.exe -m hub

# tests (whole suite)
.\.venv\Scripts\python.exe -m pytest -q
# a single test
.\.venv\Scripts\python.exe -m pytest tests/test_linkinfo.py::test_parse_netsh_wlan
```

A bare `uvicorn hub.main:app` binds 127.0.0.1 only; use `python -m hub` (or `--host 0.0.0.0`)
for other devices. No linter/formatter is configured (some `# noqa` codes exist but there is no
ruff/flake8 config); don't add one unless asked.

Docker: `docker compose up -d --build` (Tailscale sidecar, no published ports) or
`docker compose -f docker-compose.lan.yaml up -d --build` (publishes `8080`).

## Architecture

Three cooperating parts:

- **`hub/`** — FastAPI app: JSON API + server-rendered Jinja UI + SQLite + Copilot analyzer.
  Layering is strict: **routers** (`sessions`, `ingest`, `analysis`) → **`service.py`** (all
  data access) → **`db.py`** (raw sqlite3). `models.py` holds the Pydantic models that are the
  **shared API contract** for both collectors and the UI — change a field here and you touch
  collectors, the DB schema, and templates. `main.py` wires routers + static/artifact mounts;
  `config.py` centralizes all runtime config.
- **`collectors/asl_collector/`** — the capture agent (a `python -m asl_collector` CLI, plus
  `collectors/windows/*.ps1` and `collectors/linux/*.sh` wrappers). Runs on the machines under
  test, POSTs logs/link samples/net tests to the hub API. The **host** normally runs long-lived
  in `--watch` mode and the **client dictates the session** (`--create`); the host follows.
- **`network/`** — iperf3 runner + parser and per-network-path scenario presets.

Data flow: collectors → hub API (`/api/sessions/...`) → SQLite → UI renders logs side-by-side +
an RSSI/roam chart → Copilot analysis on demand. The **session** is the central entity tying
everything together (`sessions` table + `log_chunks`, `link_samples`, `net_tests`, `artifacts`,
`chat_messages`, all `ON DELETE CASCADE`).

Deployment: the hub runs LAN/WireGuard-reachable on port 8080, tailnet-only behind a Tailscale
**sidecar** (`network_mode: service:tailscale`, published via `tailscale serve`), or directly on
a host with `python -m hub`.

## Conventions

- **Collectors are standard-library only.** Anything under `collectors/asl_collector/` must run
  on an unprepared system Python with no `pip install` — use `urllib` (see `client.py`), never
  `httpx`/`requests`. The hub may use third-party deps; collectors may not.
- **Parsers are split from runners** in `linkinfo.py`/`conninfo.py`/`hostmeta.py` and the iperf
  parser; discovery is split the same way in `logfind.py` (log paths) and `appfind.py` (client
  app executables), whose `candidate_*` functions are pure and unit-tested. Pure parse functions
  take captured command text so they can be tested against the fixtures in `samples/*.txt`. When
  adding OS/command support, add a parse function + a sample + a test; keep the subprocess call
  out of the parser.
- **Config is env-vars only**, all `ASL_`-prefixed and resolved in `hub/config.py` (e.g.
  `ASL_DATA_DIR`, `ASL_COPILOT_BACKEND`, `ASL_COPILOT_TOKEN`). Zero-config defaults must keep
  working. `config.py` reads env at import time (see the test note below).
- **Copilot has three interchangeable backends** in `copilot.py`: `mock` (offline rule-based,
  the default and the always-available fallback), `cli`, `sdk`. All are fed the *same*
  `build_context(...)` structure; `cli`/`sdk` fall back to `mock` on any error. Analysis is
  opt-in per session (data leaves the box only on Analyze/chat).
- **DB access is synchronous, connection-per-call** via the `db.db()` contextmanager. JSON-typed
  columns (`encoder_settings`, `meta`) are stored as TEXT and (de)serialized in `row_to_dict`.
- **Network path taxonomy** is a fixed `Literal`: `local-LAN` / `remote-WireGuard` /
  `remote-Tailscale` / `remote-WAN`, derived from the client IP range. Reuse these values.
- The **host collector fills blank session fields live during capture** (codec/resolution/fps/
  bitrate/HDR from the log; client IP + network path from the live connection) and **never
  overrides** values already set in the UI/CLI.
- **"Awaiting a host/client" means that side has posted no log chunk yet** — never that the
  `host`/`client` *name* field is blank, since the host collector fills the client name in while
  it runs. `--attach-latest` (client) and `--watch` (host) both depend on this.
- Every module starts with `from __future__ import annotations`.
- Data lives under `data/` and secrets in `.env` — both gitignored; never commit either.

## Tests

`tests/conftest.py` prepends `collectors/` to `sys.path` (the collector package isn't at repo
root), then sets `ASL_DATA_DIR` to a temp dir and forces `ASL_COPILOT_BACKEND=mock` **before**
importing `hub` (config reads env at import). Use the `client` fixture (FastAPI `TestClient`) for
API/page tests; link/host/iperf parser tests read from `samples/`.
