# Apollo Streaming Lab

A troubleshooting + test harness for **Apollo/Sunshine** (host) ↔ **Moonlight/Artemis**
(clients) game streaming, covering **local and remote** scenarios.

Each test is a **session** that links, in one place:
- the **host** (Apollo) log and the **client** (Moonlight/Artemis) log, shown **side-by-side**,
- the **scenario/config** (network path, codec, resolution, fps, bitrate, HDR, encoder knobs),
- **network diagnostics** (iperf3),
- **auto-detected link/AP info** — Ethernet vs Wi-Fi, and on Wi-Fi the access point
  (SSID + **BSSID**), band/channel/RSSI/rate — **sampled through the session** to catch
  mid-stream **Wi-Fi roaming / signal dips**,
- your **notes / experience**, and
- an on-demand **Copilot analysis** that deciphers what happened.

The hub is viewable from **any device** (PC / TV / phone browser) over your LAN/WireGuard or tailnet.

## Architecture

```
  Apollo host (Windows)          Clients                         Hub (Docker on watchtower)
  ┌───────────────────┐   ┌─────────────────────────┐           ┌───────────────────────────┐
  │ Start-AslSession  │   │ Linux Moonlight (.sh)    │  LAN /    │ hub app (FastAPI + SQLite)│
  │  → sunshine.log   │   │ Windows Moonlight (.ps1) │ WireGuard │  side-by-side logs, RSSI  │
  │  → link/AP samples│──▶│ Android/Xbox (manual UI) │──or──────▶│  chart, notes, Copilot    │
  └───────────────────┘   └─────────────────────────┘  Tailscale└───────────────────────────┘
```

Three cooperating parts:
- **`hub/`** — FastAPI app: JSON API + server-rendered Jinja UI + SQLite + Copilot analyzer.
- **`collectors/`** — the stdlib-only capture agent (`python -m asl_collector`) plus Windows
  (`.ps1`) and Linux (`.sh`) launchers. Runs on the machines under test and POSTs logs, link
  samples, and net tests to the hub. Android/Xbox are captured manually via the hub UI.
- **`network/`** — iperf3 runner/parser + per-network-path scenario presets.

The hub is reached either over your **LAN / WireGuard** (recommended) or **tailnet-only** behind
a Tailscale sidecar with no published LAN ports — see [docs/deploy.md](./docs/deploy.md).

## Repo layout
```
hub/                 FastAPI hub: API, server-rendered UI, SQLite, Copilot analyzer
  routers/           sessions, ingest (logs/links/nettests/artifacts), analysis
  templates/ static/ side-by-side log view, RSSI/roam chart, notes, Copilot panel + chat
collectors/
  asl_collector/     shared, stdlib-only lib: link detection, log slicing/discovery, hub client, netmon
  windows/           Start-AslSession.ps1  (Apollo host or Windows Moonlight/Artemis)
  linux/             asl-session.sh        (Linux Moonlight)
network/             iperf3 runner/parser + scenario presets
deploy/              Tailscale serve config (serve.json) + ACL snippet
docs/                all documentation (see below)
samples/ tests/      sample tool output + pytest suite
Dockerfile  docker-compose.yaml  docker-compose.lan.yaml  .env.example
```

## Quickstart — run the hub locally (dev)
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Reachable only from this machine (localhost):
.\.venv\Scripts\python.exe -m uvicorn hub.main:app --reload --port 8080   # http://127.0.0.1:8080
# Reachable from other devices (binds 0.0.0.0:8080 via config):
.\.venv\Scripts\python.exe -m hub                                          # http://<this-host-ip>:8080
```
> A bare `uvicorn hub.main:app` binds to **127.0.0.1 only** — use `python -m hub` (or add
> `--host 0.0.0.0`) to reach it from other devices, and open the port in your host firewall.
> Running it on the host this way is a supported deploy (**Option C** in
> [docs/deploy.md](./docs/deploy.md)); for always-on use a Docker deploy is better.

## Capture a session (in brief)
1. Create the session on the **host** collector (`-Create`) — or in the UI (**+ New session**).
2. Run the collector on each **client**: it **attaches to the host's session automatically**
   (no id to copy — auto-picks the lone awaiting session, or pass `--attach-latest`) and
   **auto-detects the log from `--source`/`--role`** (override with `--log`).
3. Optionally run an iperf3 test (`network/iperf_runner.py`).
4. Stop the collectors, add **notes**, set the **outcome**, then click **Analyze**.

While capturing, collectors **post logs + link samples every ~30s** (`--post-interval`), so the
session page updates **live** (both the session page and the sessions list auto-refresh until the
session is stopped). The host collector fills blank session metadata (codec/res/fps/HDR, client IP
+ network path) **live during** the capture too. For a live **client** log, launch Artemis/Moonlight
via the collector (`-Launch`) so it captures the app's real-time stderr — its `%TEMP%` log file is
buffered and only flushes in bursts.

The **host** collector auto-fills blank session fields **live during the capture** (codec/
resolution/fps/bitrate/HDR from the log; client IP + network path from the live connection) and
never overrides values you set yourself. Full walkthrough (local vs remote WireGuard):
[docs/host-client-setup.md](./docs/host-client-setup.md).

## Documentation
All docs live in [`docs/`](./docs/):
- **[Host & client setup](./docs/host-client-setup.md)** — wire up host + hub + clients; per-test capture (local & remote).
- **[Deploying the hub](./docs/deploy.md)** — LAN/WireGuard vs tailnet-only, and `.env` config.
- **[Agent-less capture (Android & Xbox)](./docs/agentless-capture.md)** — manual capture via the hub UI.
- **[Copilot analysis](./docs/copilot-analysis.md)** — the `mock`/`cli`/`sdk` backends and their config.
- **[Log paths](./docs/log-paths.md)** · **[Scenario matrix](./docs/scenario-matrix.md)** · **[Troubleshooting](./docs/troubleshooting.md)**

## Testing
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

> Data lives under `data/` (gitignored); secrets go in `.env` (gitignored). Ensure all
> machines run **NTP** so host/client logs line up.
