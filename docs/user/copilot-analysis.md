# Copilot analysis

Use **Analyze** when you want help interpreting one session or a matched comparison. Session data
stays local until you click **Analyze** or send a follow-up chat message.

## What Analyze uses

The analyzer works from evidence already attached to the session:
- requested versus effective stream settings,
- iperf3 results,
- link / Wi-Fi samples,
- HDR and screenshot evidence,
- operator notes, and
- the tail of the host and client logs.

## Backends

| Backend | What it does | Needs a token? |
|---------|--------------|----------------|
| `mock` (default) | Offline, rule-based diagnosis. Always available and used as the fallback. | No |
| `cli` | Uses your installed GitHub Copilot CLI for a free-form analysis. | Yes |
| `sdk` | Uses the GitHub Copilot Python SDK for a free-form analysis. | Yes |

`cli` and `sdk` automatically fall back to `mock` on any error (missing token, missing tool,
import failure, or backend error), so **Analyze** still returns a result.

## What the offline (`mock`) analyzer can flag

**Network / link**
- iperf3 packet loss above 5% or jitter above 1 ms.
- Wi-Fi roaming when the client BSSID changes mid-session.
- Weak Wi-Fi when client RSSI falls below -70 dBm.
- Host/client NIC-speed mismatches that can cause burst loss.

**From the client's own performance summary**
- network frame drops above 1%;
- packet loss versus congestion, based on latency and jitter patterns; and
- burst loss severe enough to force an IDR/key-frame request.

**Audio**
- out-of-sequence audio near startup versus mid-stream; and
- surround Opus sessions that may overwhelm the client because it must decode and downmix 5.1/7.1
  audio.

**Logs**
- error, disconnect, timeout, codec, HDR, and decoder findings from either log tail, with common
  known-benign lines filtered out so the real finding is easier to see.

**Structured stream and HDR evidence**
- requested versus effective codec, resolution, FPS, bitrate, and HDR mode;
- HDR requested but not actually encoded or displayed end to end;
- client tone-mapping or fallback; and
- materially different HDR outcomes or operator ratings across sessions sharing the same
  comparison label.

The analysis distinguishes hard negotiation evidence from subjective visual assessment. Screenshots
and ratings help explain what you saw, but they do not establish objective HDR color accuracy
without calibrated capture hardware.

## Configuration

Set these in `.env` (see [deploy.md](./deploy.md)); the same names appear in
[`.env.example`](../../.env.example):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ASL_COPILOT_BACKEND` | `mock` | `mock` / `cli` / `sdk`. |
| `ASL_COPILOT_TOKEN` | — | GitHub token with a Copilot entitlement (`cli`/`sdk`). Falls back to `GITHUB_TOKEN`. |
| `ASL_COPILOT_MODEL` | `auto` | Model name. |
| `ASL_COPILOT_CLI_PATH` | `copilot` | Path to the Copilot CLI binary for the `cli` backend. |
| `ASL_COPILOT_LOG_TAIL_LINES` | `400` | Trailing log lines per source included in the prompt. |