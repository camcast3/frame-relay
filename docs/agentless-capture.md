# Agent-less capture (Android & Xbox)

Some clients can't run the Python collector, so their side of a session is captured **manually**
through the hub's web UI. Open the hub in the device's browser (it's reachable on the tailnet or
LAN) and use the session page's **Manual entry** panel.

> Still run the **host collector** on the Apollo host for these sessions — it captures the Apollo
> log and **auto-detects the client's IP + network path** from the live connection. Only the
> client-side log/stats and the device's network details need manual entry.

Both clients land beside the host's Apollo log in the side-by-side view, and the manual link
samples feed the RSSI/roam timeline and the Copilot analysis.

---

## Android (Artemis / Moonlight)

Android clients can't run the Python collector, so capture is manual.

### 1. Turn up client logging in Artemis
- Artemis / Moonlight: **Settings → enable verbose/extended logging** (if available).
- Reproduce the stream/issue you want to capture.

### 2. Export the client log
- In Artemis, use **Settings → Export/Share logs** (Moonlight-Android exposes a log
  export/share action). Save or share the log text to yourself.
- If no in-app export exists, capture `logcat` over USB:
  ```bash
  adb logcat -d -s Moonlight:* Artemis:* > artemis-log.txt
  ```

### 3. Add it to the session
On the hub's session page, use **Manual entry (Android / agent-less)**:
- **Paste a client log** → pick role `artemis` (or `moonlight`), set the device name, paste
  the exported log, and submit.
- **Add a Wi-Fi / link sample** → enter what the phone shows for the current network:
  - Wi-Fi **SSID** and **BSSID** (the BSSID identifies which access point — find it in the
    Android Wi-Fi details, or an app like PingMaster / a Wi-Fi analyzer),
  - band/channel, **RSSI (dBm)**, and the link/negotiated speed.
  - Add a second sample if you moved / roamed during the test so the timeline shows it.

### 4. Network test (optional)
The sanctioned iperf3 test can't be scripted from the phone. Use **PingMaster** (Android)
against the host running `iperf3 -s`, then enter the jitter/loss into the session, or run
iperf3 from another client on the same network as a proxy for path quality.

---

## Xbox (Moonlight)

Retail Xbox consoles can't run the Python collector (locked-down UWP), so Xbox capture is manual
too. On Xbox you use the **Moonlight** app.

### 1. Client-side info off the Xbox
- Enable Moonlight's **on-screen performance overlay** during the stream and note the stats
  (decode time, host/network latency, dropped frames).
- Log export on Xbox is limited — screenshot the overlay or type your observations.

### 2. Xbox network details
- Xbox → Settings → Network shows wired vs Wi-Fi and connection quality.
- Xbox can't be a WireGuard peer, so Xbox streaming is **LAN (local-LAN)**; the host collector
  confirms this from the client IP.

### 3. Add it to the session (hub UI → Manual entry panel)
- **Paste a client log** → role **moonlight**, device `Xbox`, paste the overlay stats / notes.
- **Add a Wi-Fi / link sample** → enter the Xbox's connection type and, on Wi-Fi, band/signal.
