# Troubleshooting quick reference

Common streaming failure modes and where the hub/collectors help. Sources: Apollo/Sunshine
troubleshooting docs.

| Symptom | Likely cause | What to check in the session |
|---------|--------------|------------------------------|
| Stutter only on Wi-Fi | Weak RSSI or **AP roam** mid-stream | RSSI/roam timeline (red line = BSSID change); switch to Ethernet or lock the AP/band |
| RSSI charted but **no roam detection** on a Windows client | Windows 11 24H2+ withholds the BSSID unless Location Services are on | Link samples show a blank `bssid`; enable **Settings → Privacy & security → Location** on the client — see [log-paths.md](./log-paths.md) |
| Screenshot request stays pending or is rejected | The session is no longer active, a collector is offline, or the shared screenshot token does not match | Request it from the active session page while the stream is still live, and confirm the same `ASL_SCREENSHOT_TOKEN` on the hub, host, and collector-capable client |
| Heavy packet loss, host much faster than client | **Buffer overrun** (e.g. 2.5 GbE host → 1 GbE/Wi-Fi client) | Link samples show the NIC-speed mismatch; cap host NIC or lower bitrate; Apollo > 0.23.1 helps |
| Loss/jitter on a specific path | Network path quality | iperf3 panel (loss > 5% / jitter > 1 ms is bad); lower bitrate ~15%, compare wired |
| 30–60% loss on one client only | **MTU** mismatch | Try a lower host MTU (e.g. 1428) for that guest |
| No/black video, decoder errors | Codec/HDR unsupported by client | Client log flags (HEVC/AV1/HDR); try HEVC SDR first |
| Can't connect remotely | NAT / port forwarding | Run **MIST** (Moonlight Internet Streaming Tester); attach findings to notes |
| Network test recorded nothing | **iperf3 not installed**, or the result was never posted | `iperf3` must be on **both** machines (`winget install ar51an.iPerf3` / `apt install iperf3`) and `iperf3 -s` running on the host; the runner now prints where it posted, or why it couldn't |
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

The Windows host collector independently records active CCD paths with
`QueryDisplayConfig`/`DisplayConfigGetDeviceInfo` before, during, and after each session. In the
hub's **Virtual display validation** card, check:

- the Apollo/Sunshine virtual target was active during capture,
- its source mode and refresh match the requested/effective resolution and FPS,
- Windows Advanced Color matches the requested HDR state,
- **Only active display** is yes when using `ensure_only_display`, and
- the pre-stream target set returns after disconnect.

An unknown virtual identity means Windows returned a target name/path that did not contain a
recognized Apollo/Sunshine/virtual-display marker; inspect the raw device names rather than
treating that as a pass.

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

### Read the client's own performance stats
If stereo doesn't fix it, stop guessing from the host — **the client measures the path
end-to-end**. Moonlight/Artemis writes a performance summary to its log:

```
Incoming frame rate from network: 57.48 FPS
Frames dropped by your network connection: 3.45%     <- packet loss
Frames dropped due to network jitter:      0.05%     <- congestion delay
Average network latency: 1 ms (variance: 0 ms)
```

Read them together — they separate the two failure modes:

| Pattern | Meaning | Fix |
|---------|---------|-----|
| Network drops **> 1%**, low latency + low variance, jitter drops ~0 | **Packet loss** — the link can't absorb the bitrate's bursts | Lower the bitrate until drops fall under 1%; compare a wired run |
| Jitter drops high, latency variance high | **Congestion delay** | Fix bufferbloat/QoS on the path |
| Both near zero, but you still hear gaps | Loss is **not** on the network | Look at the client's audio stack (WASAPI/underruns, power management) |

`Reached consecutive drop limit` followed by `IDR frame request sent` means a whole burst was
lost — long enough to hear as an audio gap. The hub's **Analyze** button reads all of these
automatically.

### Out-of-sequence audio: startup vs mid-stream
The client logs `Leaving fast audio recovery mode after OOS audio data (N < N+1)` when audio
packets arrive lost or reordered. **Timing decides whether it matters:**

- Within ~15s of `Initializing audio stream` → the normal initial resync. Harmless, and it
  happens on every connect and every app launch.
- **Mid-stream, well clear of any restart** → the path really is losing audio.

Line the events up against the audio (re)inits before concluding anything; the analyzer does
this split for you.

If stereo alone doesn't fix it:

1. **Lower the video bitrate.** The requested bitrate (`Client Requested bitrate is [...]` in the
   host log) is a **cap, not a constant rate** — the encoder only spends what the content needs,
   so a high number isn't continuously saturating the link. The risk is **bursts**: on scene
   changes and fast motion the encoder spikes toward the cap, and on a Wi-Fi client those spikes
   drop packets — including the small audio packets. AV1 looks excellent at ~50-80 Mbps for
   1440p/60, so caps far above that buy burst risk for no visible quality.
2. **Thin out host virtual-audio drivers.** Stacked virtual mixers (SteelSeries Sonar, Sonic
   Studio, Nahimic, etc.) sit in the capture path and are a frequent cause of crackle/dropouts.
   Disable them and set a plain physical device as the default output.
3. **Check the link.** Capture a session and look at the RSSI/roam timeline and an iperf3 run —
   loss > 5% or jitter > 1 ms will break audio before it visibly breaks video.

> **Change one variable at a time.** Fix the audio config, re-test, *then* touch the bitrate.
> Changing both at once tells you nothing about which mattered — and if stereo alone fixes it you
> keep your full bitrate headroom. Capturing each attempt as a session makes the before/after
> comparison objective instead of going by ear.

## Workflow
1. Reproduce with verbose logging on (see [log-paths.md](./log-paths.md)).
2. Capture host + client into one hub session; run iperf3.
3. Use the side-by-side view + RSSI/roam timeline to line events up.
4. Click **Analyze** and ask Copilot follow-ups (e.g. "why the stall at 12:03?").
