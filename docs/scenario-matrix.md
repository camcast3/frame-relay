# Scenario matrix (template)

Systematically walk local → remote and Ethernet → Wi-Fi so limitations are reproducible.
Create one hub session per row; the presets live in `network/scenarios.py`.

| # | Network path      | Client link      | Codec | Res/FPS   | Bitrate | HDR | Expected | Result | Session id |
|---|-------------------|------------------|-------|-----------|---------|-----|----------|--------|------------|
| 1 | local-LAN         | Ethernet         | HEVC  | 1440p/60  | 80      | off |          |        |            |
| 2 | local-LAN         | Wi-Fi 5GHz       | HEVC  | 1440p/60  | 50      | off |          |        |            |
| 3 | local-LAN         | Wi-Fi 6E/6GHz    | AV1   | 4K/60     | 100     | on  |          |        |            |
| 4 | remote-WireGuard  | Ethernet         | HEVC  | 1080p/60  | 35      | off |          |        |            |
| 5 | remote-WireGuard  | Wi-Fi            | HEVC  | 1080p/60  | 25      | off |          |        |            |
| 6 | remote-WAN        | any              | HEVC  | 1080p/60  | 25      | off |          |        |            |

For each row:
1. On the client, note the AP you're on (the collector records SSID/BSSID automatically).
2. Start the collector on the **host** and the **client** (see repo README), attach both to
   the same session id.
3. Run an iperf3 test (`network/iperf_runner.py`).
4. Stream for a few minutes; try to trigger the limitation (movement, load, roaming).
5. Stop the collectors, add your **notes**, set the **outcome**, then click **Analyze**.

## What each path stresses
- **local-LAN:** encoder/decoder latency, Wi-Fi quality, NIC-speed mismatch (buffer overrun).
- **remote-WireGuard:** tunnel MTU (try host MTU ~1420), UniFi uplink saturation, WAN jitter/loss.
- **remote-Tailscale:** DERP relay vs direct, MTU, WAN jitter/loss, encryption overhead.
- **remote-WAN:** uplink saturation, bufferbloat, NAT/firewall — use MIST for NAT diagnosis.
