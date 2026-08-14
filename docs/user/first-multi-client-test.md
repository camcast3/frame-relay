# First multi-client test

This is the canonical start-to-finish operator guide. It assumes no prior project context.

The example compares **Final Fantasy VII Remake Intergrade** across Windows Moonlight clients and
an Xbox. Replace the game, devices, and settings as needed.

## What the terms mean

- **Hub**: the web application and database that stores every test session.
- **Host collector**: runs beside Apollo and contributes the Apollo log, client IP/network path,
  link samples, and Windows virtual-display topology.
- **Client collector**: wraps Moonlight or Artemis on Windows/Linux and contributes live client
  logs and link samples.
- **Session**: one client playing one stream once.
- **Comparison label**: groups multiple sessions that are intended to be compared.
- **Requested settings**: what the client was configured to request.
- **Effective settings**: what Apollo actually negotiated and encoded.

Run clients **one at a time**. Finish or stop the current session before starting the next one.

## 1. Choose a controlled test

Use the same comparison label and controls for every device:

| Field | Example baseline |
|---|---|
| Comparison label | `ff7r-1080p60-sdr-lan-v1` |
| Apollo application preset | `Playnite` |
| Game title | `FINAL FANTASY VII REMAKE INTERGRADE` |
| Network path | `local-LAN` |
| Codec | `HEVC` |
| Resolution | `1920x1080` |
| FPS | `60` |
| Bitrate | `30 Mbps` |
| HDR | Off |
| Test duration | 10 minutes |

Use the exact Apollo preset name. If FF7 is directly registered in Apollo, use that preset name
instead of `Playnite`.

For a fair hardware comparison, use **Moonlight on every device that supports it**. Changing both
the hardware and the client app makes the result ambiguous. Compare Moonlight versus Artemis in a
separate test set.

Prefer the same connection type, ideally Ethernet. If one device uses Wi-Fi, the result measures
the device plus its network link rather than decoder hardware alone. The hub records that evidence,
but it cannot remove the confounding variable.

Choose a repeatable in-game section: the same save, scene, camera path, graphics preset, and
duration. Record the procedure in the session notes.

## 2. Start the hub

On the machine that will store the results:

```powershell
git clone https://github.com/camcast3/apollo-streaming-lab.git
cd apollo-streaming-lab
docker compose -f docker-compose.lan.yaml up -d --build
curl.exe http://127.0.0.1:8080/health
```

Find its LAN address:

```powershell
(Get-NetIPConfiguration |
  Where-Object IPv4DefaultGateway |
  Select-Object -First 1).IPv4Address.IPAddress
```

This must print a plain address such as `192.168.69.159`, not an object/table. The examples below
use:

```text
HUB=http://192.168.69.159:8080
```

Open `HUB` in a browser from another device before testing. If it does not load, allow inbound
TCP 8080 in the hub machine's firewall.

## 3. Start the Apollo host collector

On the Windows Apollo host:

```powershell
git clone https://github.com/camcast3/apollo-streaming-lab.git
cd apollo-streaming-lab
.\collectors\windows\Start-AslSession.ps1 `
  -HubUrl http://192.168.69.159:8080 `
  -Source host `
  -Watch
```

Leave it running for the entire test series. It automatically follows each new session.

Run the host collector in the logged-in interactive Windows session, not as SYSTEM or a
non-interactive service. `QueryDisplayConfig` requires access to the console desktop to validate
Apollo's virtual display.

Apollo should use debug or verbose logging. The normal log location is:

```text
C:\Program Files\Apollo\config\sunshine.log
```

## 4. Prepare collector-capable clients

Windows and Linux collectors require only Python 3; no client-side `pip install` is required.
Clone or pull the same committed repository revision on each client. Linux screenshot requests
also require one installed desktop capture tool: `grim`, `gnome-screenshot`, `scrot`, or
ImageMagick `import`. The rest of the Linux collector works without those tools.

On each Windows client:

```powershell
git clone https://github.com/camcast3/apollo-streaming-lab.git
cd apollo-streaming-lab
git pull
```

Configure Moonlight to request the exact codec, resolution, FPS, bitrate, HDR, and audio settings
defined in the test table.

If you want authenticated host/client screenshots from the active session page, generate one shared
`ASL_SCREENSHOT_TOKEN` and set it on the hub, the Apollo host, and every collector-capable client
before starting their collectors. Use the same value everywhere; mismatches are rejected. The
hub-side setting lives in `.env` (see [Deploying the hub](./deploy.md)).

## 5. Run each Windows client

For normal capture, let Apollo and Moonlight report the stream details. The recommended command is:

```powershell
.\collectors\windows\Start-AslSession.ps1 `
  -HubUrl http://192.168.69.159:8080 `
  -Source client `
  -Role moonlight `
  -Create `
  -Name "FF7R - ROG Ally" `
  -ComparisonLabel "ff7r-1080p60-sdr-lan-v1" `
  -LaunchClient `
  -StopSession
```

Only the hub URL, capture side/role, and create/attach choice are fundamental. In this comparison:

- `ComparisonLabel` is required to group the device runs; logs cannot infer your experiment name.
- `Name` is optional but makes the session list readable.
- `LaunchClient` is strongly recommended on Windows because it captures Moonlight/Artemis stderr
  live instead of relying on a buffered log.
- `StopSession` is a convenience that closes the session after the launched client exits.

The collectors fill blank fields from evidence:

| Field | Evidence source |
|---|---|
| Requested codec/resolution/FPS/bitrate/HDR | Moonlight/Artemis request log and Apollo handshake |
| Effective codec/resolution/FPS/bitrate/HDR | Apollo encoder/display log |
| Apollo application preset and game/process | Apollo selected-application/process lines, when emitted |
| Client platform/version | Collector OS and Moonlight/Artemis log |
| Network path | Live client IP observed by the Apollo host |
| Decoder/renderer/HDR display state | Moonlight/Artemis client log |

Steam and Playnite logs are not read directly today. They are less authoritative for the stream
contract and can report the launcher rather than the process Apollo captured. Apollo's own log is
used first; if that Apollo version does not emit the preset/game identity, enter it in the session
page or use the optional overrides below.

Use explicit values only when logs do not expose them or when you intentionally want to record a
known requested configuration before connection:

```powershell
  -ApolloApp "Playnite" `
  -GameTitle "FINAL FANTASY VII REMAKE INTERGRADE" `
  -ClientPlatform "ROG Ally / Windows" `
  -NetworkPath local-LAN `
  -Codec HEVC `
  -Resolution 1920x1080 `
  -Fps 60 `
  -BitrateMbps 30
```

Explicit CLI/UI values win over automatic observations and are not overwritten. Do not supply
guesses.

Change only `Name` between the hardware runs:

| Device | Name |
|---|---|
| ROG Ally | `FF7R - ROG Ally` |
| Legion laptop | `FF7R - Legion Laptop` |
| MiniPC | `FF7R - MiniPC` |

The collector creates the session and opens Moonlight. Wait 5-10 seconds at Moonlight's main
screen before starting the stream so the host watcher has time to attach. When the repeatable
scene is on screen, keep the session active long enough to run the authenticated screenshot request
from section 7. After that, finish the test section and close Moonlight. `-StopSession` performs
the final upload and marks the session stopped.

If the MiniPC runs Linux, use the equivalent command:

```bash
collectors/linux/asl-session.sh \
  --hub-url http://192.168.69.159:8080 \
  --source client --role moonlight --create \
  --name "FF7R - MiniPC" \
  --comparison-label "ff7r-1080p60-sdr-lan-v1" \
  --launch-client --stop-session
```

## 6. Run an Xbox session

Xbox cannot run the collector, so its client evidence is entered through the hub.

1. Open `HUB/sessions/new`.
2. Create a session with:
   - Name: `FF7R - Xbox - 1080p60 SDR`
   - Comparison/test case: `ff7r-1080p60-sdr-lan-v1`
   - Apollo preset: `Playnite`
   - Game/process: `FINAL FANTASY VII REMAKE INTERGRADE`
   - Client app: `moonlight`
   - Client platform: `Xbox`
   - Network path: `local-LAN`
   - Requested codec/resolution/FPS/bitrate/HDR: `HEVC`, `1920x1080`, `60`, `30`, off
3. Wait 5-10 seconds for the host watcher.
4. Enable Moonlight's performance overlay and play the same test section.
5. On the session page:
   - paste any available client log or overlay statistics;
   - add wired/Wi-Fi details;
   - upload an overlay screenshot;
   - take an Xbox screenshot of the repeatable scene and upload it as the manual client image;
   - complete **Edit stream/HDR evidence**;
   - add notes and set the outcome;
   - stop the session.

The host collector still captures Apollo logs, client IP/network path, host link data, and virtual
display evidence for the Xbox run.

## 7. Verify every session before moving on

### Request authenticated host/client screenshots while the session is active

Do this before you stop a collector-capable run.

1. Set the same `ASL_SCREENSHOT_TOKEN` on the hub, the Apollo host, and the collector-capable
   client before their collectors start.
2. While the stream is live and the repeatable scene is visible, open that active session page.
3. In **Host/client screenshot comparison**, enter the shared token. This authenticates the
   request; a mismatched token is rejected.
4. Click **Request host + client screenshots**.
5. Wait for both request rows to show **completed**, then review the pair side by side and record
   any timing or visual differences in the notes.

Each collector fulfills the request on its next poll, so the captures are near simultaneous rather
than frame-perfect. Windows HDR desktop capture may be tone-mapped by the OS, and protected
content/surfaces may capture as black. Treat the images as corroborating visual evidence, not
objective HDR measurement.

Xbox and other agent-less clients cannot fulfill the automated client-side request. Take the Xbox
screenshot manually at the same scene and upload it on the session page beside the host image.

Open the session page and confirm:

- host Apollo log is present;
- client log is present, or Xbox/manual evidence was entered;
- Apollo preset and game title are correct;
- requested and effective codec/resolution/FPS/bitrate match;
- virtual-display validation is pass or has an understood partial reason;
- HDR stages are populated for an HDR test;
- link samples show the expected Ethernet/Wi-Fi path;
- performance overlay screenshot is attached;
- automated host/client screenshots are completed, or the manual agent-less client
  screenshot was uploaded;
- notes describe the exact test scene and subjective result;
- outcome is set;
- session status is stopped.

Do not start the next client while the previous session remains active.

## 8. Compare the clients

After all runs, open:

```text
HUB/comparisons/ff7r-1080p60-sdr-lan-v1
```

The comparison page first reports whether the controlled fields match. Resolve or explain any
mismatch before attributing a difference to the client hardware.

Click **Analyze** on a session for deterministic offline findings. The default `mock` backend
does not require GitHub Copilot or a token. Configuring the `cli` or `sdk` backend adds free-form
Copilot analysis but is optional.

## 9. Run HDR separately

Do not mix SDR and HDR sessions under one label. Create a second controlled test, for example:

```text
ff7r-4k60-hdr-lan-v1
```

Use the same procedure with a common HDR-capable resolution, HEVC/AV1 choice, bitrate, display
mode, and in-game scene. The hub records:

- client HDR request;
- host display and encoded HDR state;
- Windows Advanced Color state on the virtual display;
- client decoder/renderer/display state;
- tone mapping or fallback;
- operator visual rating and screenshots.

Screenshots can reveal obvious clipping, washed-out color, black-level, or brightness differences,
but objective HDR color accuracy requires calibrated external capture hardware.

## Quick troubleshooting

| Symptom | Check |
|---|---|
| Hub does not open from another device | Hub firewall TCP 8080 and `docker compose ... ps` |
| Host side stays empty | Host watcher is running in `-Watch`; Apollo log path and debug logging |
| Client log is missing on Windows | Use `-LaunchClient` so stderr is captured live |
| Virtual-display result is partial | Host collector must run interactively; inspect raw display names |
| Comparison says not compatible | Correct the label, app/game, requested settings, host, or network path |
| Multiple sessions attach incorrectly | Keep only one active session at a time |
| Xbox has little client data | Enable overlay, screenshot it, and complete manual evidence fields |

See [Host & client setup](./host-client-setup.md), [Agent-less capture](./agentless-capture.md),
and [Troubleshooting](./troubleshooting.md) for deeper reference.
