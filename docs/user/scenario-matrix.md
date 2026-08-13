# Scenario matrix (template)

Systematically walk local → remote and Ethernet → Wi-Fi so limitations are reproducible.
Create one hub session per row and reuse an explicit comparison/test-case label for matched runs
that should compare cleanly.

| # | Network path      | Client link      | Codec | Res/FPS   | Bitrate | HDR | Expected | Result | Session id |
|---|-------------------|------------------|-------|-----------|---------|-----|----------|--------|------------|
| 1 | local-LAN         | Ethernet         | HEVC  | 1440p/60  | 80      | off |          |        |            |
| 2 | local-LAN         | Wi-Fi 5GHz       | HEVC  | 1440p/60  | 50      | off |          |        |            |
| 3 | local-LAN         | Wi-Fi 6E/6GHz    | AV1   | 4K/60     | 100     | on  |          |        |            |
| 4 | remote-WireGuard  | Ethernet         | HEVC  | 1080p/60  | 35      | off |          |        |            |
| 5 | remote-WireGuard  | Wi-Fi            | HEVC  | 1080p/60  | 25      | off |          |        |            |
| 6 | remote-WAN        | any              | HEVC  | 1080p/60  | 25      | off |          |        |            |

For each row:
1. On the client, note the AP you're on (the collector records SSID/BSSID automatically — on
   Windows clients the BSSID needs Location Services on, see [log-paths.md](./log-paths.md)).
2. Leave the **host** collector running in `-Watch` mode, then start the **client** with
   `-Create`; the host joins the session the client created within seconds (see
   [host-client-setup.md](./host-client-setup.md)).
3. Run an iperf3 test (`network/iperf_runner.py`).
4. Stream for a few minutes; try to trigger the limitation (movement, load, roaming). Logs +
   link samples post live (~30s), so the session page fills in while you watch.
5. Stop the client, add your **notes**, set the **outcome**, then click **Analyze**.

## Moonlight vs Artemis matched comparison

Vary only the client app/platform. Keep the same host, Apollo application preset, game/process,
requested codec/resolution/FPS/bitrate/HDR mode, and network path. Give every run the same
test-case label; the comparison page reports any recorded mismatch before treating the sessions
as comparable. Capture the same in-game scene and overlay where possible. Screenshots and
operator ratings are useful for washed-out color, clipping, black-level, or brightness
differences, but are subjective without calibrated capture hardware.

## What each path stresses
- **local-LAN:** encoder/decoder latency, Wi-Fi quality, NIC-speed mismatch (buffer overrun).
- **remote-WireGuard:** tunnel MTU (try host MTU ~1420), UniFi uplink saturation, WAN jitter/loss.
- **remote-Tailscale:** DERP relay vs direct, MTU, WAN jitter/loss, encryption overhead.
- **remote-WAN:** uplink saturation, bufferbloat, NAT/firewall — use MIST for NAT diagnosis.
