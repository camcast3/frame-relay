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
| Stuck on H.264, no HEVC/AV1 offered | **Encoder ran on a software adapter** — no hardware GPU available to the captured display | Host log: `Found H.264 encoder: libx264 [software]`. See [No hardware encoder / no AV1](#no-hardware-encoder--no-av1) below |
| Audio dropouts / stuttering audio on the client | **7.1 surround** requested by the client — 8-channel Opus the client must decode and downmix | Host log: `Opus initialized: 48 kHz, 8 channels, 2048 kbps`. See [Audio dropouts](#audio-dropouts) below |
| Session page shows no client logs/samples mid-capture | Collector posts on a timer, not instantly | Collectors flush every `--post-interval` (~30s) and the page auto-refreshes; wait one interval, or press **Enter** to force a final flush. `client` IP / network-path are filled by the **host** collector |
| Client (Artemis) logs only appear at stream end | Artemis **buffers** its `%TEMP%` log, flushing in bursts | Launch Artemis via the collector (`-Launch`) to capture its **stderr live** — see [log-paths.md](./log-paths.md) |

## No hardware encoder / no AV1

If the host log shows `Found H.264 encoder: libx264 [software]` and **every** hardware encoder
fails during the probe, the problem is almost never the codec — it's that the encoder's D3D11
device landed on an adapter with **no media engine**:

```
Info: Trying encoder [nvenc] / [quicksync] / [amdvce]
Warning: Unknown GPU vendor ID: 00001414
Device Description : Microsoft Basic Render Driver     <- WARP software adapter
Device Vendor ID   : 0x00001414                        <- 0x1414 = Microsoft (not 0x1002 AMD / 0x10DE NVIDIA)
Device Video Mem   : 0 MiB
Error: Failed to create encoder D3D11 device [0x887A0004]   <- DXGI_ERROR_UNSUPPORTED
Info: Encoder [amdvce] failed
```

The encoder must run on the adapter that owns the **captured display**. In a headless /
virtual-display setup (`headless_mode`, `isolated_virtual_display_option`) the virtual display is
an *indirect display driver* — it does no rendering of its own and borrows a GPU. If no hardware
GPU is available, Windows composes it on the **Microsoft Basic Render Driver** and all hardware
codecs disappear.

**Check the GPU is actually usable by Windows** (a disabled GPU is the usual cause):

```powershell
Get-PnpDevice -Class Display | Select-Object Status, Problem, FriendlyName
```

`CM_PROB_DISABLED` (problem code 22) = disabled. Note `Enable-PnpDevice` can silently fail to
take effect here; `pnputil` is more reliable (run elevated):

```powershell
pnputil /enable-device  "PCI\VEN_1002&DEV_XXXX&..."   # instance id from the command above
pnputil /restart-device "PCI\VEN_1002&DEV_XXXX&..."   # forces the driver to attach
```

After enabling, a device may briefly report `CM_PROB_FAILED_ADD` — the `/restart-device` above
clears it. Confirm the driver attached (`Status=OK`, `Problem=CM_PROB_NONE`), then **restart
Apollo** so it re-probes encoders (it caches the result at startup). Success looks like:

```
Device Description : AMD Radeon RX 7900 XTX
Device Vendor ID   : 0x00001002
Device Video Mem   : 24560 MiB
Info: Found H.264 encoder: h264_amf [amdvce]
Info: Found HEVC encoder: hevc_amf [amdvce]
Info: Found AV1 encoder:  av1_amf  [amdvce]
```

### Verifying it survived a reboot
The enable is persistent only if the PnP **`ConfigFlags`** disable bit is clear — `Enable-PnpDevice`
can clear that flag while still failing to start the device, which looks confusing (`ConfigFlags=0x0`
*and* `CM_PROB_DISABLED`). After a reboot, confirm both the device state and the encoder:

```powershell
# 1. GPU must be OK / CM_PROB_NONE (bit 0x1 of ConfigFlags = disabled at boot)
Get-PnpDevice -Class Display | Select-Object Status, Problem, FriendlyName

# 2. Apollo must still find the hardware encoders
Select-String -Path "C:\Program Files\Apollo\config\sunshine.log" -Pattern 'Found .* encoder'
```

Expect `Found AV1 encoder: av1_amf [amdvce]` — if you instead see `libx264 [software]`, the GPU
came up disabled again; re-run the `pnputil` steps above and look for whatever re-disabled it
(scheduled task, driver update, or a manual Device Manager disable).

### Keeping prompts on the streamed display
A common reason people disable the GPU/monitor in the first place is that UAC prompts and windows
land on the **physical** monitor instead of the streamed virtual display. Don't disable the GPU
(that kills hardware encoding) — use Apollo's display-device option instead:

```
dd_configuration_option = ensure_only_display   # deactivate other displays, activate only this one
dd_config_revert_on_disconnect = enabled        # restore the physical monitor on disconnect
```

`ensure_primary` only makes the virtual display *primary* and leaves the physical monitor
**active**, so dialogs can still open there. `ensure_only_display` removes it from the desktop
topology for the duration of the session — the host log shows the recomputed topology collapsing
to the single virtual display.

> AV1 **encode** on AMD requires **RDNA3 (RX 7000) or newer**; RDNA2 and older can decode AV1 but
> not encode it. Media servers like Plex/Jellyfin playing AV1 only prove *decode*, not encode.

## Audio dropouts

Brief gaps of silence or stuttering audio on the client, while **video stays smooth** and the
host log shows **no audio errors**, usually means the client can't keep up with the audio stream
rather than anything being wrong on the host.

Check what the host negotiated — it logs the sink and Opus setup at the start of every session:

```
Info: Selected audio sink: virtual-Surround 7.1{...}
Info: Changed virtual audio sink format to [S24 48000 7.1]
Info: Opus initialized: 48 kHz, 8 channels, 2048 kbps (total), LOWDELAY
```

**8 channels / 2048 kbps is the 7.1 path** — 4x the bitrate of stereo (`2 channels, 512 kbps`),
and the client must decode 8-channel Opus and **downmix it** to whatever it actually outputs.
On handhelds and phones that decode+downmix is a common source of dropouts.

The **client** chooses this, not the host — Apollo just selects a matching virtual sink, so the
host's audio settings can be entirely at defaults and you'll still get 7.1. Fix it on the client:

- **Artemis / Moonlight → Settings → Audio configuration → Stereo**, then reconnect.

Confirm from the host log that the next session reports `2 channels, 512 kbps`. Unless you are
genuinely outputting to a 5.1/7.1 receiver, stereo is the better choice — downmixed surround
sounds no better than stereo on handheld speakers or headphones.

If stereo alone doesn't fix it:

1. **Lower the video bitrate.** Audio and video share one connection; a very high request (the
   client asks for it — check `Client Requested bitrate is [...]` in the host log) can starve
   audio packets on a Wi-Fi client. Try ~60-80 Mbps.
2. **Thin out host virtual-audio drivers.** Stacked virtual mixers (SteelSeries Sonar, Sonic
   Studio, Nahimic, etc.) sit in the capture path and are a frequent cause of crackle/dropouts.
   Disable them and set a plain physical device as the default output.
3. **Check the link.** Capture a session and look at the RSSI/roam timeline and an iperf3 run —
   loss > 5% or jitter > 1 ms will break audio before it visibly breaks video.

## Workflow
1. Reproduce with verbose logging on (see [log-paths.md](./log-paths.md)).
2. Capture host + client into one hub session; run iperf3.
3. Use the side-by-side view + RSSI/roam timeline to line events up.
4. Click **Analyze** and ask Copilot follow-ups (e.g. "why the stall at 12:03?").
