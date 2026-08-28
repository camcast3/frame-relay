# Deploying the hub

The hub is a small FastAPI + SQLite app. There are three supported deployments — pick the one
that matches how your devices reach it. For the day-to-day capture workflow that sits on top of a
running hub, see [host-client-setup.md](./host-client-setup.md).

| Option | Command | Reachable at | When to use |
|--------|---------|--------------|-------------|
| **LAN / WireGuard** (recommended) | `docker compose -f docker-compose.lan.yaml up -d --build` | `http://<hub-host>:8080` | Devices are on your LAN or reach it over an operator-managed **WireGuard** tunnel. |
| **Tailnet-only** | Requires a maintainer-reviewed tracked image update, then `docker compose up -d --build` | `https://frame-relay.<tailnet>.ts.net` | Only when an aged, scan-clean Tailscale image is available. |
| **Direct on the host** (no Docker) | `python -m frame_relay` | `http://<host-ip>:8080` | Run it on the Windows/Linux machine you already use — no Docker. Bind to all interfaces + open the firewall to reach it from other devices. |

The Docker options read Copilot settings from `.env` (copy `.env.example` first) and persist data
in the `hub-data` volume (`/data` in the container → the SQLite DB + uploaded artifacts).

---

## Option A — LAN / WireGuard (recommended)

Publishes port `8080` on the Docker host. Local devices hit the LAN IP directly; remote devices
may reach the same IP through an operator-managed WireGuard route. Access control is your
firewall's job — this option has no built-in gate.

```powershell
# on the Docker host
copy .env.example .env    # set Copilot and screenshot-request secrets as needed
docker compose -f docker-compose.lan.yaml up -d --build
docker compose -f docker-compose.lan.yaml ps
```

Then open `http://<hub-host>:8080`. If remote clients use WireGuard, allow their configured client
CIDR to reach the hub on TCP 8080. `TS_AUTHKEY` is **not** needed for this option.

---

## Option B — Tailnet-only (Tailscale sidecar)

The hub runs with `network_mode: service:tailscale` and is published to the tailnet by
`tailscale serve` on `:443` — it has **no LAN ports**. Nothing bridges the gaming VLAN ↔ DMZ.

This option intentionally has no default image. As of 2026-08-13, every official Tailscale image
available under the seven-day holdback had at least one known critical vulnerability, including
the current `latest`. The Compose file therefore fails closed instead of silently starting a
known-vulnerable privileged sidecar. Use LAN/WireGuard until a reviewed image passes:

```powershell
docker scout cves --only-severity critical,high --exit-code `
  tailscale/tailscale:<version>@sha256:<digest>
```

1. Copy `.env.example` to `.env`.
2. Have a maintainer replace the intentionally invalid image in `docker-compose.yaml` with an
   official version+digest that is at least seven days old and passes the scan above, then commit
   that reviewable change.
3. Set `TS_AUTHKEY` from the Tailscale admin console; prefer an auth key tagged
   `tag:frame-relay-hub`.
4. Optionally set `FRAME_RELAY_COPILOT_TOKEN` and `FRAME_RELAY_COPILOT_BACKEND=cli` or `sdk`
   (see [copilot-analysis.md](./copilot-analysis.md)).
5. Apply [`../../deploy/tailscale-acl.snippet.hujson`](../../deploy/tailscale-acl.snippet.hujson) in the
   Tailscale admin console (defines `tag:frame-relay-hub` / `tag:frame-relay-collector` and who
   may reach the hub on `tcp:443`).
6. Start on the Docker host:

   ```powershell
   docker compose up -d --build
   docker compose ps
   ```

7. Open `https://frame-relay.<tailnet>.ts.net` from a tailnet device.
8. Confirm the hub is **not** reachable at `http://<LAN-IP>:8080` — this compose file publishes
   no LAN ports.

The proxy mapping (`:443` → `127.0.0.1:8080`, funnel disabled) lives in
[`../../deploy/serve.json`](../../deploy/serve.json).

---

## Option C — Run directly on the host (no Docker)

Handy when you want the hub on the machine you already use (e.g. the Apollo host) without Docker.
`python -m frame_relay` binds `FRAME_RELAY_HOST`/`FRAME_RELAY_PORT` (**`0.0.0.0:8080`** by default), so it listens on all
interfaces and is reachable from other devices right away:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
.\.venv\Scripts\python.exe -m frame_relay  # serves http://<host-ip>:8080 on all interfaces
```

A **bare `uvicorn hub.main:app` binds `127.0.0.1` only** (localhost) — that's why it isn't
reachable from other devices. To use uvicorn directly, pass `--host 0.0.0.0`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn hub.main:app --host 0.0.0.0 --port 8080
```

Then, on the host:

1. **Open the port in the firewall.** On Windows (run PowerShell as admin) allow inbound TCP 8080:
   ```powershell
   New-NetFirewallRule -DisplayName "Frame Relay hub" -Direction Inbound `
       -Action Allow -Protocol TCP -LocalPort 8080 -Profile Any `
       -RemoteAddress 10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10
   ```
   On Linux use your firewall (e.g. `sudo ufw allow 8080/tcp`).
2. **Find the host's LAN IP** (`ipconfig` on Windows / `ip addr` on Linux) and browse to
   `http://<host-ip>:8080` from another device. That IP:port is the `HUB` URL you give the
   collectors.

If the host works locally but not from another device, test on the client:

```powershell
Test-NetConnection <hub-ip> -Port 8080
```

A failed test after the private-range firewall rule usually means the router blocks inter-VLAN
traffic or the Wi-Fi SSID has guest/client isolation enabled. Allow the client VLAN to reach the
hub IP on TCP 8080; do not expose 8080 to the public internet.

Data goes to `./data` next to the repo (override with `FRAME_RELAY_DATA_DIR`). This runs in the
foreground with no auto-restart — for always-on use prefer a Docker option above (or wrap it in a
service, e.g. NSSM on Windows or a systemd unit on Linux). The hub has no built-in auth, so anyone
who can reach `:8080` can use it — keep it on a trusted LAN or gate access with your firewall /
WireGuard.

---

## Configuration (`.env`)

All runtime settings come from environment variables. The same names are listed in
[`.env.example`](../../.env.example):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TS_AUTHKEY` | — | Tailscale auth key (Option B only). |
| `FRAME_RELAY_COPILOT_BACKEND` | `mock` | `mock` / `cli` / `sdk` — see [copilot-analysis.md](./copilot-analysis.md). |
| `FRAME_RELAY_COPILOT_TOKEN` | — | GitHub token with a Copilot entitlement (`cli`/`sdk`). Falls back to `GITHUB_TOKEN`. |
| `FRAME_RELAY_COPILOT_MODEL` | `auto` | Copilot model name. |
| `FRAME_RELAY_SCREENSHOT_TOKEN` | — | Shared secret required to queue and fulfill on-demand host/client screenshot requests. Leave blank to disable the feature. |
| `FRAME_RELAY_DATA_DIR` | `/data` (Docker) · `./data` (direct) | Where the SQLite DB + artifacts live. |
| `FRAME_RELAY_HOST` / `FRAME_RELAY_PORT` | `0.0.0.0` / `8080` | Bind address/port for `python -m frame_relay` (and inside the container). |

Data lives under `data/` and secrets in `.env` — both are gitignored; never commit either.

Generate a screenshot token, store it in the hub's `.env`, and set the identical
`FRAME_RELAY_SCREENSHOT_TOKEN` environment variable on every collector-capable host/client:

```powershell
$token = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$token
```

Screenshot requests are disabled when the hub token is blank. Xbox and other agent-less clients
still require manual screenshot upload.
