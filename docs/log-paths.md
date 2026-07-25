# Log paths & logging knobs (per platform)

Confirmed sources the collectors read from. **Turn logging up before testing** and make sure
every machine runs **NTP** — the hub correlates host and client logs by timestamp.

## Apollo / Sunshine host (Windows)
- **Log file:** `log_path` in the Apollo config (default `sunshine.log` in Apollo's config
  dir). Typical install paths:
  - `%ProgramFiles%\Apollo\config\sunshine.log`
  - `%ProgramFiles%\Sunshine\config\sunshine.log`
- **Verbosity:** set `min_log_level` to `debug` (or `verbose`) in the Web UI → Configuration,
  or the config file. Lines are timestamped and include client connect/pair/disconnect events.
- The `Start-AslSession.ps1` launcher auto-discovers these paths for `-Source host`.

## Moonlight-based clients (Windows) — Artemis & Moonlight-Qt
Both are Qt apps that write a **per-run** diagnostic log into `%TEMP%`:
- **Artemis** (Apollo's Moonlight fork — "Artemis Desktop Project"): `%TEMP%\Artemis-<n>.log`.
  Grab the newest run and pass it to the collector:
  ```powershell
  $log = (Get-ChildItem "$env:TEMP\Artemis-*.log" |
          Sort-Object LastWriteTime -Desc | Select-Object -First 1).FullName
  # ... -Source client -Role artemis -LogPath $log
  ```
- **Moonlight-Qt:** use the app's **Copy diagnostic logs** action and save the file, then pass it
  with `-LogPath` (`-Role moonlight`).
  > Heads-up: `%TEMP%\Moonlight_Game_Streaming_Client_*.log` is the **installer** (WiX/Burn) log,
  > *not* a stream log — don't attach it.
- `-LogPath` accepts globs, but the collector posts **every** match, so prefer selecting the single
  newest file as shown above.

## Moonlight-Qt client (Linux — Bazzite couch box)
- **Flatpak:** `~/.var/app/com.moonlight_stream.Moonlight/` (and `flatpak run … 2> moonlight.log`).
- **Native:** `~/.config/Moonlight Game Streaming Project/`.
- Pass the file(s) with `--log` to `asl-session.sh`.

## Artemis client (Android) — agent-less
- In-app **Export/Share logs**, or `adb logcat -d -s Moonlight:* Artemis:* > artemis-log.txt`.
- Paste into the session via the hub's **Manual entry** panel. See
  [agentless-capture.md](./agentless-capture.md).

## Link / access-point detection
Captured automatically by the collectors (see `collectors/asl_collector/linkinfo.py`):
- **Windows:** `netsh wlan show interfaces` (SSID/BSSID/band/channel/radio/signal/rate) and
  `Get-NetAdapter` (wired link speed).
- **Linux:** `iw dev <dev> link` (BSSID/freq/signal dBm/bitrate), `nmcli` (fallback),
  `ethtool <dev>` (wired speed).
- **BSSID = the specific access point.** A BSSID change between samples = a Wi-Fi roam.
- Android: entered manually (agent-less).

## Network test
- iperf3 (sanctioned by the Apollo docs), port **5201** TCP/UDP:
  - host: `iperf3 -s`
  - client: `iperf3 -c <host> -t 60 -u -R -b <bitrate>`
- Good path: **loss < 5%, jitter < 1 ms**. Driven by `network/iperf_runner.py`.
