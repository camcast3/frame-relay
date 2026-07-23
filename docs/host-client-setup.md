# Host & client setup — local and remote

How to wire up the **Apollo host**, the **hub**, and each **Moonlight/Artemis client** for the
two scenarios you test:

- **Local** — devices are on your LAN and connect normally.
- **Remote** — devices connect through your **UniFi WireGuard** server (each device has its own
  provisioned `.conf`). Remote clients land on the **WireGuard VLAN `192.168.2.0/24`**.

> This app does **not** manage WireGuard — bring your own tunnel (UniFi provisions the confs).
> You control VLAN/firewall segmentation; the notes below only say what must be reachable.

Every test involves two things a device talks to: the **Apollo host** (the stream) and the
**hub** (records the session). Both are reached over the LAN locally, or over WireGuard remotely.

---

## A. One-time: Apollo host (Windows)
1. Install Apollo and pair your clients.
2. **Turn logging up:** Web UI → Configuration → `min_log_level = debug` (or `verbose`).
   Log file: `C:\Program Files\Apollo\config\sunshine.log`.
3. **Firewall:** allow Apollo's ports on the interfaces clients use (LAN, and the WG-routed
   path): TCP `47984/47989/48010`, UDP `47998-48000`.
4. **Remote reachability:** ensure WireGuard clients (`192.168.2.x`) can route to the host's IP.
   With WG terminating on the UniFi router this is a firewall/route rule you own — no port
   forwarding needed.

## B. One-time: hub (on watchtower)
Pick the deployment that matches how your devices connect:

- **LAN + WireGuard (matches your setup):**
  ```bash
  docker compose -f docker-compose.lan.yaml up -d --build
  ```
  Hub is at `http://<watchtower-ip>:8080`. Local devices hit that IP directly; remote devices
  reach the same IP over WireGuard. Allow the WG VLAN → hub:8080 in your firewall.
- **Tailnet-only (optional):** `docker compose up -d --build` (Tailscale sidecar, `tailscale
  serve`); reachable only at `https://apollo-streaming-lab.<tailnet>.ts.net`. Use this if you'd
  rather not expose a LAN port. See [../deploy/README.md](../deploy/README.md).

Set `ASL_COPILOT_BACKEND` / `ASL_COPILOT_TOKEN` in `.env` if you want real Copilot analysis.

Below, `HUB` = the URL from this step (e.g. `http://192.168.86.246:8080`).

---

## C. Per test — LOCAL (LAN)
Create the session on the **host** (it auto-fills codec/resolution/fps/bitrate/HDR from the log
and the client IP + network path from the live connection), then attach each client to its id.

**Host — Apollo (Windows):**
```powershell
collectors\windows\Start-AslSession.ps1 -HubUrl HUB -Create -Name "couch LAN HEVC" -Source host
# prints the new session id
```

**Client — Linux Moonlight (couch box):**
```bash
collectors/linux/asl-session.sh --hub-url HUB --session-id <id> --source client --role moonlight \
    --interval 15 --log "$HOME/.var/app/com.moonlight_stream.Moonlight/config/.../Moonlight.conf"
```

**Client — Windows Moonlight/Artemis:**
```powershell
collectors\windows\Start-AslSession.ps1 -HubUrl HUB -SessionId <id> -Source client -Role moonlight `
    -LogPath "$env:TEMP\Moonlight\Moonlight.log"
```

**Client — Android Artemis:** use the session page's **Manual entry** panel (paste the exported
log + enter Wi-Fi/AP details). See [../collectors/android/README.md](../collectors/android/README.md).

Stream for a few minutes, then press **Enter** in each collector window. Add `-StopSession` /
`--stop-session` if you want the session auto-marked stopped.

---

## D. Per test — REMOTE (WireGuard)
Same as local, with three differences:

1. **Bring up WireGuard first** on the remote device (its UniFi-provisioned `.conf`), then point
   Moonlight/Artemis at the host's LAN IP (reachable through the tunnel) and connect.
2. **`HUB`** is the watchtower IP reachable over WireGuard (same `http://<watchtower-ip>:8080`,
   as long as your firewall lets the WG VLAN reach it).
3. The host collector already defaults the WireGuard subnet to `192.168.2.0/24`, so a remote
   client is classified **`remote-WireGuard`** automatically. Override only if your WG VLAN
   differs:
   ```powershell
   collectors\windows\Start-AslSession.ps1 -HubUrl HUB -Create -Name "remote WG HEVC" -Source host `
       -WgSubnet 192.168.2.0/24
   ```

**iperf3 over the tunnel** (port 5201; open it to the WG VLAN on the host):
```bash
# host:
iperf3 -s
# remote client (via WG):
python network/iperf_runner.py --host <host-ip-over-wg> --hub-url HUB --session-id <id>
```

---

## E. Network-path classification (how the collector labels a session)
| Client IP seen by the host | Network path      |
|----------------------------|-------------------|
| `192.168.2.0/24` (WG VLAN) | **remote-WireGuard** |
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
