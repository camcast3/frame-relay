# Host & client setup — local and remote

How to wire up the **Apollo host**, the **hub**, and each **Moonlight/Artemis client** for two
common scenarios:

- **Local** — devices are on your LAN and connect normally.
- **Remote** — devices connect through an operator-managed **WireGuard** tunnel.

> This app does **not** manage WireGuard. You control tunnel provisioning, routing, and firewall
> segmentation; the notes below only say what must be reachable.

Every test involves two things a device talks to: the **Apollo host** (the stream) and the
**hub** (records the session). Both are reached over the LAN locally, or over WireGuard remotely.

---

## A. One-time: Apollo host (Windows)
1. Install Apollo and pair your clients.
2. **Turn logging up:** Web UI → Configuration → `min_log_level = debug` (or `verbose`).
   Log file: `C:\Program Files\Apollo\config\sunshine.log`.
3. **Firewall:** allow Apollo's ports on the interfaces clients use (LAN, and the WG-routed
   path): TCP `47984/47989/48010`, UDP `47998-48000`.
4. **Remote reachability:** ensure the configured WireGuard client CIDR can route to the host's
   IP. This is a firewall/route rule you own; port forwarding is usually unnecessary when the
   tunnel terminates inside your network.

## B. One-time: hub
Pick the deployment that matches how your devices connect:

- **LAN + WireGuard:**
  ```bash
  docker compose -f docker-compose.lan.yaml up -d --build
  ```
  Hub is at `http://<hub-host>:8080`. Local devices hit that IP directly; remote devices can reach
  the same IP over WireGuard when routing and firewall rules allow it.
- **Tailnet-only (optional):** `docker compose up -d --build` (Tailscale sidecar, `tailscale
  serve`); reachable only at `https://frame-relay.<tailnet>.ts.net`. Use this if you'd
  rather not expose a LAN port. See [deploy.md](./deploy.md).

Set `FRAME_RELAY_COPILOT_BACKEND` / `FRAME_RELAY_COPILOT_TOKEN` in `.env` if you want real Copilot analysis.

If you want on-demand host/client screenshots from the active session page, also set the same
`FRAME_RELAY_SCREENSHOT_TOKEN` on the hub, the Apollo host, and every collector-capable client before
starting their collectors. The operator flow is in [first-multi-client-test.md](./first-multi-client-test.md).

Below, `HUB` = the URL from this step. Documentation examples use
`http://192.0.2.10:8080`; replace that reserved example address with your actual hub address.

---

## C. Per test — LOCAL (LAN)

### Recommended: host watches, client dictates
The **host is always on, so run it once and leave it running.** In `-Watch` mode it waits for
whichever session the client creates, captures into it, then goes back to waiting — no session
id, no restart between tests. It is idempotent: a session leaves the "awaiting host" list as
soon as the host posts to it, so restarting the watcher never double-captures.

**Host — Apollo (Windows), start once and leave it:**
```powershell
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source host -Watch
```

**Client — dictates the session** by creating it when you start a test:
```powershell
# Windows Artemis: the collector wraps the app - it finds Artemis for -Role, launches it, and
# captures its stderr live. Capture ends when you close Artemis.
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source client -Role artemis -Create `
    -Name "couch LAN AV1" -ComparisonLabel "game-local-hdr" -ApolloApp Playnite `
    -GameTitle "Test game" -LaunchClient
```
```bash
# Linux Moonlight (finds the Flatpak export or /usr/bin/moonlight)
collectors/linux/frame-relay-session.sh --hub-url HUB --source client --role moonlight --create \
    --name "couch LAN AV1" --comparison-label "game-local-hdr" --apollo-app Playnite \
    --game-title "Test game" --launch-client --interval 15
```

For couch use, the same flow can be attached to an existing Steam shortcut on either platform.
The setup asks whether the client is Moonlight or Artemis, installs shared artwork, and prints one
Launch Options line to paste manually. See
[Steam Game Mode / Big Picture launcher](./steam-game-mode.md).

The host back-fills its log from the session's start time, so the connect/handshake lines are
captured even though the host joined a moment later. It moves on when the session is stopped or
when the next one starts.

On a Windows host, the collector also samples the active display paths through
`QueryDisplayConfig`/`DisplayConfigGetDeviceInfo` before, during, and after the stream. The session
page checks that the Apollo/Sunshine virtual target appeared with the expected resolution,
refresh rate, and Advanced Color/HDR state, then verifies that the original topology returned.

Use the same comparison label, Apollo preset/game, requested settings, and network path on the
Moonlight and Artemis runs. The hub verifies those controls before presenting the client/HDR
results as a matched comparison.

### Alternative: host creates, clients attach
Still supported if you'd rather drive from the host. It auto-fills codec/resolution/fps/bitrate/
HDR from the log and the client IP + network path from the live connection. **Clients don't need
the session id** — they attach to the session the host just created (auto-picked when it's the
only one awaiting a client, or pass `-AttachLatest` / `--attach-latest` to always take the
newest). The **log location is auto-detected from `-Source`/`-Role`** too.

**Host — Apollo (Windows):**
```powershell
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Create -Name "couch LAN HEVC" -Source host
# prints the new session id (for reference only — clients attach automatically)
```

**Client — Linux Moonlight (couch box):**
```bash
collectors/linux/frame-relay-session.sh --hub-url HUB --source client --role moonlight --attach-latest \
    --interval 15
# Moonlight-Qt log auto-detected under ~/.var/app/... or ~/.config/...; add --log if yours differs
```

**Client — Windows Moonlight/Artemis:**
```powershell
# Artemis: newest %TEMP%\Artemis-*.log is found automatically
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source client -Role artemis -AttachLatest
# For LIVE client logs, let the collector wrap the app (its %TEMP% log is buffered; stderr is
# real-time). -LaunchClient finds the app for -Role; capture runs until you close it:
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source client -Role artemis -AttachLatest `
    -LaunchClient
# Non-standard install? Point at the executable instead:
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source client -Role artemis -AttachLatest `
    -Launch "D:\Games\Artemis\Artemis.exe"
# Moonlight-Qt on Windows has no fixed log path — wrap it the same way, or pass -LogPath:
collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source client -Role moonlight -AttachLatest `
    -LaunchClient
```

> Prefer to be explicit? Pass `-SessionId <id>` / `--session-id <id>` instead of `-AttachLatest`.
> With neither, the collector attaches automatically when exactly one session is awaiting a
> client, and only prompts you to choose when several are.

**Client — Android Artemis:** use the session page's **Manual entry** panel (paste the exported
log + enter Wi-Fi/AP details). See [agentless-capture.md](./agentless-capture.md).

**Client — Xbox (Moonlight):** agent-less (no Python on Xbox) → use the **Manual entry** panel
(role `moonlight`); the host collector still auto-detects the Xbox's IP + network path. See
[agentless-capture.md](./agentless-capture.md).

Stream for a few minutes — the collectors **post logs + link samples to the hub every ~30s**, so
the session page updates **live** while you watch (it auto-refreshes until the session is
stopped). Then stop the **client** capture (press **Enter**, or close the app when you used
`-Launch`) for a final flush. A host in `-Watch` mode needs no attention: it finishes the session
when you stop it in the UI (or with `-StopSession` on the client) and then waits for the next
one. Tune the cadence with `-PostIntervalSeconds` / `--post-interval` (`0` = post only on stop).

---

## D. Per test — REMOTE (WireGuard)
Same as local, with three differences:

1. **Bring up WireGuard first** on the remote device, then point
   Moonlight/Artemis at the host's LAN IP (reachable through the tunnel) and connect.
2. **`HUB`** is the hub IP reachable over WireGuard (same `http://<hub-host>:8080`,
   as long as your firewall lets the WG VLAN reach it).
3. Tell the host collector which client CIDR belongs to WireGuard so those connections are
   classified **`remote-WireGuard`**:
   ```powershell
   collectors\windows\Start-FrameRelaySession.ps1 -HubUrl HUB -Source host -Watch `
       -WgSubnet <wireguard-client-cidr>
   ```

**iperf3 over the tunnel** (port 5201; open it to the WG VLAN on the host). **iperf3 must be
installed on both machines** — that is the usual reason a test records nothing:
```bash
# host:
iperf3 -s
# remote client (via WG) — omit --session-id and it attaches to the newest active session:
python network/iperf_runner.py --host <host-ip-over-wg> --hub-url HUB
```

---

## E. Network-path classification (how the collector labels a session)
| Client IP seen by the host | Network path      |
|----------------------------|-------------------|
| configured `--wg-subnet` / `-WgSubnet` CIDR | **remote-WireGuard** |
| other private (RFC1918)    | **local-LAN**     |
| `100.64.0.0/10`            | **remote-Tailscale** (only if you use Tailscale) |
| public                     | **remote-WAN**    |

Change/extend the WireGuard subnet with `--wg-subnet <cidr>` (repeatable) on the collector, or
`-WgSubnet` on the PowerShell launcher.

---

## F. Suggested order
Walk the [scenario matrix](./scenario-matrix.md): local Ethernet → local Wi-Fi → remote
WireGuard (Ethernet) → remote WireGuard (Wi-Fi). Set the **outcome** and **notes** on each
session, then click **Analyze** to have Copilot compare them.
