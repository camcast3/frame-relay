# Troubleshooting quick reference

Common streaming failure modes and where the hub/collectors help. Sources: Apollo/Sunshine
troubleshooting docs.

| Symptom | Likely cause | What to check in the session |
|---------|--------------|------------------------------|
| Stutter only on Wi-Fi | Weak RSSI or **AP roam** mid-stream | RSSI/roam timeline (red line = BSSID change); switch to Ethernet or lock the AP/band |
| Heavy packet loss, host much faster than client | **Buffer overrun** (e.g. 2.5 GbE host → 1 GbE/Wi-Fi client) | Link samples show the NIC-speed mismatch; cap host NIC or lower bitrate; Apollo > 0.23.1 helps |
| Loss/jitter on a specific path | Network path quality | iperf3 panel (loss > 5% / jitter > 1 ms is bad); lower bitrate ~15%, compare wired |
| 30–60% loss on one client only | **MTU** mismatch | Try a lower host MTU (e.g. 1428) for that guest |
| No/black video, decoder errors | Codec/HDR unsupported by client | Client log flags (HEVC/AV1/HDR); try HEVC SDR first |
| Can't connect remotely | NAT / port forwarding | Run **MIST** (Moonlight Internet Streaming Tester); attach findings to notes |
| Can't pair / web UI | Credentials / firewall | Apollo log pairing lines; `sunshine --creds <user> <pass>` |
| Session page shows no client logs/samples mid-capture | Collector posts on a timer, not instantly | Collectors flush every `--post-interval` (~30s) and the page auto-refreshes; wait one interval, or press **Enter** to force a final flush. `client` IP / network-path are filled by the **host** collector |
| Client (Artemis) logs only appear at stream end | Artemis **buffers** its `%TEMP%` log, flushing in bursts | Launch Artemis via the collector (`-Launch`) to capture its **stderr live** — see [log-paths.md](./log-paths.md) |

## Workflow
1. Reproduce with verbose logging on (see [log-paths.md](./log-paths.md)).
2. Capture host + client into one hub session; run iperf3.
3. Use the side-by-side view + RSSI/roam timeline to line events up.
4. Click **Analyze** and ask Copilot follow-ups (e.g. "why the stall at 12:03?").
