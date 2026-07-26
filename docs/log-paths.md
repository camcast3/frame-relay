# Log paths & logging knobs (per platform)

Confirmed sources the collectors read from. **Turn logging up before testing** and make sure
every machine runs **NTP** — the hub correlates host and client logs by timestamp.

> **Auto-detection:** omit `--log` / `-LogPath` and the collector resolves the log from
> `--source`/`--role` per platform (`collectors/asl_collector/logfind.py`). The paths below are
> exactly what it looks for; pass `--log` only to override or when a path isn't listed.

## Apollo / Sunshine host (Windows)
- **Log file:** `log_path` in the Apollo config (default `sunshine.log` in Apollo's config
  dir). Typical install paths:
  - `%ProgramFiles%\Apollo\config\sunshine.log`
  - `%ProgramFiles%\Sunshine\config\sunshine.log`
- **Verbosity:** set `min_log_level` to `debug` (or `verbose`) in the Web UI → Configuration,
  or the config file. Lines are timestamped and include client connect/pair/disconnect events.
- The collector auto-detects these paths for `-Source host` / `-Role apollo` (override with
  `--log`).

## Moonlight-based clients (Windows) — Artemis & Moonlight-Qt
Both are Qt apps that write a **per-run** diagnostic log into `%TEMP%`:
- **Artemis** (Apollo's Moonlight fork — "Artemis Game Streaming"): `%TEMP%\Artemis-<launch_ms>.log`
  (one file per launch, named after the process start time). Its config/cache live under
  `%LOCALAPPDATA%\Artemis Desktop Project\Artemis\` (boxart, controller DB, Qt pipeline cache — no
  live log there); UI settings are Qt `QSettings` in the registry.
  - With `-Role artemis` the collector **auto-detects the newest run** — no `-LogPath` needed. To
    pin a specific run instead:
    ```powershell
    $log = (Get-ChildItem "$env:TEMP\Artemis-*.log" |
            Sort-Object LastWriteTime -Desc | Select-Object -First 1).FullName
    # ... -Source client -Role artemis -LogPath $log
    ```
  - ⚠️ **The `%TEMP%` log is heavily buffered** — Artemis flushes it in large bursts (often only
    near stream end), so tailing the file is **not live**. For a live client log, launch Artemis
    **through the collector** so it captures the process's **stderr** in real time (Qt writes the
    same log to stderr and flushes each line):
    ```powershell
    collectors\windows\Start-AslSession.ps1 -HubUrl HUB -Source client -Role artemis -AttachLatest `
        -Launch "$env:ProgramFiles\Artemis Game Streaming\Artemis.exe"
    ```
    The capture then runs until you close Artemis (or Ctrl+C). Common install path:
    `C:\Program Files\Artemis Game Streaming\Artemis.exe`.
- **Moonlight-Qt:** no fixed log path (auto-detection returns nothing on Windows) — either launch
  it via `-Launch` (same stderr capture) or use the app's **Copy diagnostic logs** action and pass
  the saved file with `-LogPath` (`-Role moonlight`).
  > Heads-up: `%TEMP%\Moonlight_Game_Streaming_Client_*.log` is the **installer** (WiX/Burn) log,
  > *not* a stream log — don't attach it.
- `-LogPath` accepts globs, but the collector posts **every** match, so prefer selecting the single
  newest file as shown above.

## Moonlight-Qt client (Linux — Bazzite couch box)
- **Flatpak:** `~/.var/app/com.moonlight_stream.Moonlight/` (and `flatpak run … 2> moonlight.log`).
- **Native:** `~/.config/Moonlight Game Streaming Project/`.
- With `-Role moonlight` the collector auto-detects `*.log` under those dirs; pass the file(s)
  with `--log` to `asl-session.sh` to override or if your install differs.

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
- **Windows 11 24H2+ hides the BSSID unless Location Services are on.** Windows treats a
  BSSID as location data, so `netsh wlan show interfaces` omits it and prints a permission
  notice. SSID/band/channel/signal still work — the only thing lost is **roam detection**.
  Enable **Settings → Privacy & security → Location** on the client to capture it; the
  collector prints a one-time note when it detects this.
- Android: entered manually (agent-less).

## Network test
- iperf3 (sanctioned by the Apollo docs), port **5201** TCP/UDP. **Install it on both machines**
  (`winget install ar51an.iPerf3`, or `apt`/`dnf install iperf3`) — a missing binary is the usual
  reason a run records nothing:
  - host: `iperf3 -s`
  - client: `python network/iperf_runner.py --host <host-ip> --hub-url <hub>`
    (omit `--session-id` and it attaches to the newest active session)
- Good path: **loss < 5%, jitter < 1 ms**. Driven by `network/iperf_runner.py`.
