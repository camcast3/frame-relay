# Copilot analysis

Every session has an on-demand **Analyze** button and a follow-up **chat**. Analysis is
**opt-in per session** — session data (scenario, iperf3 results, link samples, and the tail of
both logs) only leaves the box when you click **Analyze** or ask a chat question.

The analyzer lives in [`hub/copilot.py`](../hub/copilot.py) and has three interchangeable
backends selected by `ASL_COPILOT_BACKEND`. All three receive the *same* structured context from
`build_context(...)`, so switching backends never changes what Copilot sees.

| Backend | What it does | Needs a token? |
|---------|--------------|----------------|
| `mock` (default) | Offline, rule-based diagnosis. No network, always available. Doubles as the fallback. | No |
| `cli` | Shells out to the Copilot CLI (`copilot -p <prompt> -s --no-ask-user [--model <model>]`). | Yes |
| `sdk` | Embeds the GitHub Copilot Python SDK (imported lazily). | Yes |

`cli` and `sdk` **fall back to `mock`** on any error (missing token, CLI not found, import
failure, non-zero exit), appending a short note about what failed — so the feature never breaks.

## What the offline (`mock`) analyzer detects
Even with no token it flags the common Apollo/Sunshine failure modes from the session data.

**Network / link**
- **iperf3 packet loss > 5%** or **jitter > 1 ms** on a net test.
- **Wi-Fi roam** — more than one client BSSID during the session (a mid-stream AP change).
- **Weak Wi-Fi** — client RSSI below −70 dBm.
- **NIC-speed mismatch** — host Ethernet faster than the client's (buffer-overrun packet loss).

**From the client's own performance summary** (Moonlight/Artemis measures the path end-to-end,
so this is more reliable than inferring from the host)
- **Network frame drops > 1%** — the path is losing packets.
- **Loss vs congestion** — low latency + low variance + ~no jitter drops means packet *loss*,
  so the advice is to lower the bitrate rather than chase latency.
- **Consecutive drop limit** — a burst was lost outright, forcing an IDR/key-frame request.

**Audio**
- **Out-of-sequence audio**, split by timing: events within 15s of an audio (re)init are the
  normal startup resync and are reported as benign; **mid-stream** events mean real audio loss.
- **Surround Opus** — the client asked for 5.1/7.1 and must decode and downmix it.

**Logs**
- Error/disconnect/timeout/codec/HDR/decoder keywords in either log tail, with **known-benign
  lines filtered out** (Apollo's encoder probe deliberately provokes failures, Artemis probes
  command endpoints Apollo doesn't implement, and request URLs match on `hdrMode=`). Without
  that filter the real finding gets buried.

It then prints a prioritized "likely focus" conclusion.

**Structured stream and HDR evidence**
- Client-requested codec/resolution/FPS/bitrate versus Apollo's effective values.
- HDR requested while the host display or encoded stream remained SDR.
- Apollo encoded HDR but the client display path reported SDR.
- Client tone mapping/fallback and partial/failed HDR outcomes.
- Different HDR outcomes or materially different operator ratings across sessions sharing a
  matched comparison/test-case label.

The analysis distinguishes negotiation evidence from subjective visual assessment. Screenshots
and ratings cannot establish objective HDR color accuracy without calibrated external capture
hardware and test patterns.

## Configuration
Set these in `.env` (see [deploy.md](./deploy.md)); resolved in [`hub/config.py`](../hub/config.py):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ASL_COPILOT_BACKEND` | `mock` | `mock` / `cli` / `sdk`. |
| `ASL_COPILOT_TOKEN` | — | GitHub token with a Copilot entitlement (`cli`/`sdk`). Falls back to `GITHUB_TOKEN`. |
| `ASL_COPILOT_MODEL` | `auto` | Model name; `auto` uses the app default (no `--model` flag). |
| `ASL_COPILOT_CLI_PATH` | `copilot` | Path to the Copilot CLI binary (`cli` backend). |
| `ASL_COPILOT_LOG_TAIL_LINES` | `400` | Trailing log lines per source included in the prompt. |
