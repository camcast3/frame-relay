# Xbox (Moonlight) — agent-less capture

Retail Xbox consoles can't run the Python collector (locked-down UWP), so Xbox capture is
**manual** via the hub — like Android. On Xbox you use the **Moonlight** app.

> Still run the **host collector** on the Apollo host for the session — it captures the Apollo
> log and **auto-detects the Xbox's client IP + network path** from the live connection. Only
> the client-side log/stats and the Xbox's network details need manual entry.

## 1. Client-side info off the Xbox
- Enable Moonlight's **on-screen performance overlay** during the stream and note the stats
  (decode time, host/network latency, dropped frames).
- Log export on Xbox is limited — screenshot the overlay or type your observations.

## 2. Xbox network details
- Xbox → Settings → Network shows wired vs Wi-Fi and connection quality.
- Xbox can't be a WireGuard peer, so Xbox streaming is **LAN (local-LAN)**; the host collector
  confirms this from the client IP.

## 3. Add it to the session (hub UI → Manual entry panel)
- **Paste a client log** → role **moonlight**, device `Xbox`, paste the overlay stats / notes.
- **Add a Wi-Fi / link sample** → enter the Xbox's connection type and, on Wi-Fi, band/signal.

The client column and link data then sit beside the host's Apollo log for side-by-side analysis.
