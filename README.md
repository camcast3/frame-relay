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

The hub is viewable from **any device** on the tailnet (PC / TV / phone browser).

## Architecture

```
  Apollo host (Windows)          Clients                         Hub (Docker on watchtower)
  ┌───────────────────┐   ┌─────────────────────────┐           ┌───────────────────────────┐
  │ Start-AslSession  │   │ Linux Moonlight (.sh)    │           │ tailscale sidecar          │
  │  → sunshine.log   │   │ Windows Moonlight (.ps1) │  Tailscale│  (own netns, `serve` 443) │
  │  → link/AP samples│──▶│ Android Artemis (manual) │──────────▶│ hub app (FastAPI+SQLite)  │
  └───────────────────┘   └─────────────────────────┘  (WGmesh) │  network_mode: service:ts │
                                                                 │  Copilot analysis (opt-in)│
                                                                 └───────────────────────────┘
```

- **Tailnet-only:** the hub has **no published LAN ports**; collectors reach it over Tailscale
  via its MagicDNS name. Nothing bridges the gaming VLAN ↔ DMZ.
- **Tailscale runs as a Docker sidecar** (the hub uses `network_mode: service:tailscale`).

## Repo layout
```
hub/                 FastAPI hub: API, server-rendered UI, SQLite, Copilot analyzer
  routers/           sessions, ingest (logs/links/nettests/artifacts), analysis
  templates/ static/ side-by-side log view, RSSI/roam chart, notes, Copilot panel + chat
collectors/
  asl_collector/     shared, stdlib-only lib: link detection, log slicing, hub client, netmon
  windows/           Start-AslSession.ps1  (Apollo host or Windows Moonlight/Artemis)
  linux/             asl-session.sh        (Linux Moonlight)
  android/           agent-less capture guide (paste log + manual link entry)
network/             iperf3 runner/parser + scenario presets
deploy/              Tailscale serve config, ACL snippet, deploy runbook
docs/                log paths, scenario matrix, troubleshooting
samples/ tests/      sample tool output + pytest suite
Dockerfile docker-compose.yaml .env.example
```

## Quickstart — run the hub locally (dev)
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn hub.main:app --reload --port 8080
# open http://127.0.0.1:8080
```

## Deploy on watchtower (tailnet-only)
See [deploy/README.md](./deploy/README.md). In short: set `TS_AUTHKEY` (and optionally
`ASL_COPILOT_TOKEN`) in `.env`, then `docker compose up -d --build`, and apply
[deploy/tailscale-acl.snippet.hujson](./deploy/tailscale-acl.snippet.hujson) in the Tailscale
admin console. The hub is then at `https://apollo-streaming-lab.<tailnet>.ts.net`.

## Capture a session
1. Create a session in the UI (**+ New session**) — or let a collector create it with `--create`.
2. On the **host** and each **client**, run the collector and attach to the session id:
   ```powershell
   # Windows Apollo host
   collectors\windows\Start-AslSession.ps1 -HubUrl https://apollo-streaming-lab.<tailnet>.ts.net `
       -SessionId <id> -Source host
   ```
   ```bash
   # Linux Moonlight client
   collectors/linux/asl-session.sh --hub-url https://apollo-streaming-lab.<tailnet>.ts.net \
       --session-id <id> --source client --role moonlight --interval 15 --log <moonlight-log>
   ```
   Android (Artemis): use the hub's **Manual entry** panel — see
   [collectors/android/README.md](./collectors/android/README.md).
3. Optional network test:
   ```bash
   # host: iperf3 -s   |   client:
   python network/iperf_runner.py --host <host-ip> --hub-url <hub> --session-id <id>
   ```
4. Stop the collectors, add **notes**, set the **outcome**, then click **Analyze**.

## What the host collector fills in automatically
When run with `--source host`, on stop the collector **fills blank session fields** (never
overriding values you set in the UI/CLI):
- from the Apollo log — **codec, resolution, fps, bitrate, HDR**;
- from the live connection to Apollo's ports — the **client** IP and the **network path**
  (`100.64.0.0/10` → `remote-Tailscale`, private → `local-LAN`, public → `remote-WAN`);
- `host`/`client` also default to the capturing machine's hostname.

So a bare `--create --source host` still ends up populated after a stream.

## Copilot analysis
Set `ASL_COPILOT_BACKEND`:
- `mock` (default) — offline, rule-based diagnosis (roams, loss/jitter, log errors, NIC
  mismatch). No token, no data leaves the box.
- `cli` — shells out to the Copilot CLI (`copilot -p … -s --no-ask-user`).
- `sdk` — embeds the GitHub Copilot Python SDK.

`cli`/`sdk` need `ASL_COPILOT_TOKEN` (a GitHub token with a Copilot entitlement). Analysis is
**opt-in per session** (logs are only sent when you click Analyze / ask a chat question).

## Testing
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

> Data lives under `data/` (gitignored); secrets go in `.env` (gitignored). Ensure all
> machines run **NTP** so host/client logs line up.
