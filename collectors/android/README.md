# Android (Artemis) — agent-less capture

Android clients can't run the Python collector, so capture is **manual** via the hub's
web UI (open the hub in the phone's browser — it's reachable on the tailnet).

## 1. Turn up client logging in Artemis
- Artemis / Moonlight: **Settings → enable verbose/extended logging** (if available).
- Reproduce the stream/issue you want to capture.

## 2. Export the client log
- In Artemis, use **Settings → Export/Share logs** (Moonlight-Android exposes a log
  export/share action). Save or share the log text to yourself.
- If no in-app export exists, capture `logcat` over USB:
  ```bash
  adb logcat -d -s Moonlight:* Artemis:* > artemis-log.txt
  ```

## 3. Add it to the session
On the hub's session page, use **Manual entry (Android / agent-less)**:
- **Paste a client log** → pick role `artemis` (or `moonlight`), set the device name, paste
  the exported log, and submit.
- **Add a Wi-Fi / link sample** → enter what the phone shows for the current network:
  - Wi-Fi **SSID** and **BSSID** (the BSSID identifies which access point — find it in the
    Android Wi-Fi details, or an app like PingMaster / a Wi-Fi analyzer),
  - band/channel, **RSSI (dBm)**, and the link/negotiated speed.
  - Add a second sample if you moved / roamed during the test so the timeline shows it.

## 4. Network test (optional)
The sanctioned iperf3 test can't be scripted from the phone. Use **PingMaster** (Android)
against the host running `iperf3 -s`, then enter the jitter/loss into the session, or run
iperf3 from another client on the same network as a proxy for path quality.

That's it — the pasted log appears in the **client** column beside the host's Apollo log,
and your manual link samples feed the RSSI/roam timeline and the Copilot analysis.
